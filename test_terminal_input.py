"""Keyboard sequence and native Windows wheel regressions."""

import ctypes
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal_input import InputDecoder, WindowsConsoleInput


class InputDecoderTests(unittest.TestCase):
    def decode(self, data):
        decoder = InputDecoder()
        decoder.feed(data, now=0)
        events = []
        while (event := decoder.read(now=0)) is not None:
            events.append(event)
        return events

    def test_arrow_formats_and_modifiers_do_not_quit(self):
        self.assertEqual(self.decode("\x1b[A\x1b[B\x1b[C\x1b[D"),
                         ["up", "down", "right", "left"])
        self.assertEqual(self.decode("\x1bOA\x1bOD\x1b[1;5C"), ["up", "left", "right"])

    def test_split_escape_sequence_waits_for_completion(self):
        decoder = InputDecoder()
        decoder.feed("\x1b", now=0)
        self.assertIsNone(decoder.read(now=0.01))
        decoder.feed("[", now=0.02)
        self.assertIsNone(decoder.read(now=0.02))
        decoder.feed("A", now=0.03)
        self.assertEqual(decoder.read(now=0.03), "up")

    def test_standalone_escape_and_escape_followed_by_command(self):
        decoder = InputDecoder()
        decoder.feed("\x1b", now=0)
        self.assertEqual(decoder.read(now=0.06), "escape")
        self.assertEqual(self.decode("\x1br"), ["escape", "r"])

    def test_wheel_reports_and_clicks_are_consumed_whole(self):
        self.assertEqual(self.decode("\x1b[<64;12;15M\x1b[<65;12;15M"),
                         ["wheel_up", "wheel_down"])
        self.assertEqual(self.decode("\x1b[<68;12;15M"), ["wheel_up"])
        self.assertEqual(self.decode("\x1b[<0;12;15M\x1b[<0;12;15mq"), ["q"])
        self.assertEqual(self.decode("\x1b[<64;12;15m\x1b[<66;12;15Mq"), ["q"])
        self.assertEqual(self.decode("\x1b[M" + chr(96) + "!!"), ["wheel_up"])

    def test_fragmented_mouse_and_unknown_sequences_do_not_type_garbage(self):
        decoder = InputDecoder()
        decoder.feed("\x1b[<64;", now=0)
        self.assertIsNone(decoder.read(now=0))
        decoder.feed("12;15Mp", now=0.01)
        self.assertEqual(decoder.read(now=0.01), "wheel_up")
        self.assertEqual(decoder.read(now=0.01), "p")
        self.assertEqual(self.decode("\x1b[5~\x1b[<badMstatus\r"), list("status") + ["enter"])

    def test_ctrl_c_backspace_and_burst_text(self):
        self.assertEqual(self.decode("Cstatus\r\x08\x03"),
                         list("cstatus") + ["enter", "backspace", "quit"])


class WindowsConsoleTests(unittest.TestCase):
    def make_reader(self):
        def get_mode(handle, ptr):
            ptr._obj.value = 0x247
            return 1

        kernel = SimpleNamespace(
            GetStdHandle=Mock(return_value=1), GetConsoleMode=Mock(side_effect=get_mode),
            SetConsoleMode=Mock(return_value=1), GetNumberOfConsoleInputEvents=Mock(return_value=1),
            ReadConsoleInputW=Mock(return_value=1))
        return WindowsConsoleInput(kernel), kernel

    def test_windows_arrows_repeat_wheel_direction_and_restoration(self):
        reader, kernel = self.make_reader()
        if os.name == "nt":
            self.assertEqual(ctypes.sizeof(reader.record_type), 20)
        record = reader.record_type()
        record.kind = 1
        record.event.key.down = 1
        record.event.key.repeat = 2
        record.event.key.vk = 0x26
        reader.decode(record)
        self.assertEqual([reader.read(), reader.read()], ["up", "up"])
        record.kind = 2
        record.event.mouse.flags = 4
        record.event.mouse.buttons = 120 << 16
        reader.decode(record)
        self.assertEqual(reader.read(), "wheel_up")
        record.event.mouse.buttons = (0x10000 - 120) << 16
        reader.decode(record)
        self.assertEqual(reader.read(), "wheel_down")
        reader.restore()
        kernel.SetConsoleMode.assert_called_with(1, 0x247)
        mode = kernel.SetConsoleMode.call_args_list[0].args[1]
        self.assertTrue(mode & 0x10)
        self.assertFalse(mode & (0x40 | 0x200))

    def test_native_ctrl_c_and_discarded_mouse_motion(self):
        reader, _ = self.make_reader()
        record = reader.record_type()
        record.kind = 2
        record.event.mouse.flags = 1
        reader.decode(record)
        self.assertFalse(reader.pending)
        record.kind = 1
        record.event.key.down = 1
        record.event.key.char = "\x03"
        reader.decode(record)
        self.assertEqual(reader.read(), "quit")


if __name__ == "__main__":
    unittest.main()
