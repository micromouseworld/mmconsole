import cmd
import os
import pickle
from pprint import pprint
from traceback import print_exc

from bluetooth import RFCOMM
from bluetooth import BluetoothSocket
from bluetooth.btcommon import BluetoothError
from osbrain import Agent
from osbrain import run_agent
from osbrain import run_nameserver


def complete_subcommands(text, subcommands):
    if not text:
        return subcommands
    return [c for c in subcommands if c.startswith(text)]


class SerialInterface:
    def __init__(self):
        raise NotImplementedError()

    def send(self, message):
        raise NotImplementedError()

    def receive(self):
        raise NotImplementedError()


class BluetoothInterface:
    def __init__(self):
        self.rfcomm = BluetoothSocket(RFCOMM)
        self.rfcomm.connect(("00:21:13:01:D1:59", 1))
        self.rfcomm.settimeout(0.01)

    def send(self, message):
        try:
            self.rfcomm.send(message)
        except Exception:
            print_exc()

    def receive(self):
        return self.rfcomm.recv(1024)


class Proxy(Agent):
    def on_init(self):
        self.raw_log = []
        self.log = []
        self.buffer = ""

    def setup(self, interface_class):
        self.interface = interface_class()
        self.each(0, "receive")

    def process_log(self, log):
        log = log.rstrip()
        self.raw_log.append(log)
        log = log.split(",", 3)
        try:
            log[0] = float(log[0])
        except ValueError:
            pass
        if log[2] == "ERROR":
            print(log)
        self.log.append(log)

    def process_received(self, received):
        self.buffer += received.decode()
        splits = self.buffer.splitlines(True)
        if splits[-1].endswith("\n"):
            self.buffer = ""
        else:
            self.buffer = splits.pop()
        for log in splits:
            self.process_log(log)
        return len(splits) - 1

    def receive(self):
        try:
            received = self.interface.receive()
            return self.process_received(received)
        except BluetoothError as error:
            if str(error) != "timed out":
                raise
        return 0

    def tail(self, n):
        return self.log[-n:]

    def get_battery_voltage(self):
        self.interface.send("battery\0")


class Console(cmd.Cmd):
    prompt = ">>> "
    LOG_SUBCOMMANDS = ["all", "clear", "save"]
    CONNECT_SUBCOMMANDS = ["bluetooth", "serial"]

    def cmdloop(self, intro=None):
        """Modified cmdloop() to handle keyboard interruptions."""
        while True:
            try:
                super().cmdloop(intro="")
                self.postloop()
                break
            except KeyboardInterrupt:
                print("^C")
                self.interrupted = True
                return False

    def emptyline(self):
        """Do nothing on empty line."""
        pass

    def preloop(self):
        self.interrupted = False

    def postloop(self):
        if not self.interrupted:
            self.ns.shutdown()

    def do_connect(self, extra):
        """Connect to the robot."""
        self.ns = run_nameserver()
        self.proxy = run_agent("proxy", base=Proxy)
        if extra == "bluetooth":
            self.proxy.after(0, "setup", interface_class=BluetoothInterface)
        elif extra == "serial":
            self.proxy.after(0, "setup", interface_class=SerialInterface)
        else:
            print('Unsupported connection "{}"'.format(extra))

    def do_battery(self, *args):
        """Get battery voltage."""
        print(self.proxy.get_battery_voltage())

    def do_clear(self, *args):
        """Clear screen."""
        os.system("clear")

    def do_log(self, extra):
        """Get the full log."""
        if extra == "all":
            pprint(self.proxy.get_attr("log"))
        elif extra == "raw":
            print("\n".join(self.proxy.get_attr("raw_log")))
        elif extra == "clear":
            self.proxy.set_attr(log=[])
        elif extra == "save":
            fname = "log.pkl"
            pickle.dump(self.proxy.get_attr("log"), open(fname, "wb"))
            print('Saved log as "%s".' % fname)
        elif extra.isnumeric():
            pprint(self.proxy.tail(int(extra)))
        else:
            pprint(self.proxy.tail(10))

    def complete_log(self, text, line, begidx, endidx):
        return complete_subcommands(text, self.LOG_SUBCOMMANDS)

    def complete_connect(self, text, line, begidx, endidx):
        return complete_subcommands(text, self.CONNECT_SUBCOMMANDS)

    def do_exit(self, *args):
        """Exit shell."""
        return True

    def do_EOF(self, line):  # noqa: N802
        """Exit shell."""
        return True


if __name__ == "__main__":
    Console().cmdloop()
