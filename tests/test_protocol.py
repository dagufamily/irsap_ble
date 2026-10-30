"""Protocol tests built from real captures (no Home Assistant needed).

Run: python3 -m unittest discover -s tests   (from the irsap_ble folder, with PYTHONPATH=custom_components/irsap_ble/..)
"""
import importlib.util
from pathlib import Path
import unittest
import zlib

spec = importlib.util.spec_from_file_location(
    "irsap_protocol", Path(__file__).parent.parent / "custom_components" / "irsap_ble" / "protocol.py"
)
protocol = importlib.util.module_from_spec(spec)
import sys
sys.modules["irsap_protocol"] = protocol
spec.loader.exec_module(protocol)

# State records as read from a real radiator (tail of the data returned by the status characteristic)
PROGRAM_ON = (
    "0021011002" "0121011001" "02210120320321022 0b40004210220c80005210220f00006210220e1000721041"
    "0f02ce16a08210220c80009218c4001" "0a210220f1000b210220e1000c210410f02ce16a0d210110000e"
).replace(" ", "")
OFF = (
    "0021011002" "0121011000" "0221012032032102 20b40004210220c80005210220f00006210220f00007210110000821"
    "0220c80009218c4001" "0a210220f2000b210120320c210410ffffffff0d210110000e"
).replace(" ", "")
MANUAL = (
    "0021011001" "0121011001" "022101203203210220b40004210220c80005210220dc0006210220f000072101100008"
    "210220c80009218c4001" "0a210220f1000b210220dc000c210410ffffffff0d210110000e"
).replace(" ", "")


class TestProtocol(unittest.TestCase):
    def test_crc_and_lengths(self):
        for cmd in (1, 2, 3, 4):
            announce, blob = protocol.build_command(cmd, temp=22.0 if cmd in (3, 4) else None, hours=2 if cmd == 3 else None)
            self.assertEqual(zlib.crc32(blob[:-4]).to_bytes(4, "little"), blob[-4:])
            self.assertEqual(int.from_bytes(announce[4:6], "little"), len(blob))
            self.assertEqual(len(announce), 44)

    def test_manual_sets_record_05_only(self):
        _, blob = protocol.build_command(4, temp=21.5, now=1793130000)
        self.assertIn(bytes.fromhex("05210220d700"), blob)
        self.assertEqual(blob[107], 1)  # mode record = manual
        self.assertEqual(blob[112], 1)  # on

    def test_program_comfort(self):
        _, blob = protocol.build_command(2, now=1793130000)
        self.assertIn(bytes.fromhex("05210220f000"), blob)
        _, blob = protocol.build_command(2, comfort=23.5, now=1793130000)
        self.assertIn(bytes.fromhex("05210220eb00"), blob)
        self.assertEqual(blob[107], 2)  # program

    def test_off(self):
        _, blob = protocol.build_command(1, now=1793130000)
        self.assertEqual(blob[112], 0)

    def test_temporary_expiry_rounded_to_hour(self):
        _, blob = protocol.build_command(3, temp=22.5, hours=12, now=1793130000)
        k = blob.find(bytes.fromhex("07210410"))
        expiry = int.from_bytes(blob[k + 4 : k + 8], "little")
        self.assertEqual(expiry % 3600, 0)
        self.assertEqual(expiry, (1793130000 + 12 * 3600) // 3600 * 3600)
        self.assertIn(bytes.fromhex("06210220e100"), blob)

    def test_status_requests(self):
        reqs = protocol.build_status_requests(now=1793130000)
        self.assertEqual([len(r) for r in reqs], [44, 44])
        self.assertEqual(reqs[0][:4], bytes([0, 0, 0, 1]))
        self.assertEqual(reqs[1][:4], bytes([2, 0, 0, 1]))

    def test_parse_program(self):
        st = protocol.parse_state(b"\0" * 10 + bytes.fromhex(PROGRAM_ON))
        self.assertEqual((st.mode, st.is_on, st.current_temp, st.target_temp), ("program", True, 24.1, 22.5))
        self.assertIsNotNone(st.expiry)
        self.assertEqual(st.presets, {"antifreeze": 5.0, "eco": 18.0, "comfort": 24.0})

    def test_parse_off(self):
        st = protocol.parse_state(b"\0" * 10 + bytes.fromhex(OFF))
        self.assertEqual((st.mode, st.is_on, st.current_temp, st.target_temp, st.expiry), ("program", False, 24.2, 5.0, None))

    def test_parse_manual(self):
        st = protocol.parse_state(b"\0" * 10 + bytes.fromhex(MANUAL))
        self.assertEqual((st.mode, st.is_on, st.target_temp, st.expiry), ("manual", True, 22.0, None))

    def test_parse_garbage(self):
        self.assertIsNone(protocol.parse_state(b"\x01\x02\x03"))


if __name__ == "__main__":
    unittest.main()
