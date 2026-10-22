import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

from xmu_rollcall import rollcall_handler as handler, tui, verify
from test_rollcall_activity import rollcall


class SubmissionShortcutTests(unittest.TestCase):
    def test_skip_submits_current_code_without_reaching_target(self):
        for target in (10, '50%'):
            for attendance in ((0, 20), None):
                with self.subTest(target=target, attendance=attendance):
                    session = Mock()
                    session.headers = {}
                    session.put.return_value.status_code = 200
                    wait = Mock(side_effect=[False, True])
                    with patch.object(handler, 'get_rollcall_settings', return_value={'wait_before_answer': target}), patch.object(
                        verify, 'get_number_rollcall_info', return_value=('0026', 'ongoing', None, None)
                    ), patch.object(handler, '_fetch_attendance', return_value=attendance), patch.object(
                        tui, 'submission_shortcut', return_value=nullcontext(wait)
                    ), patch.object(verify.time, 'sleep'):
                        data = {'rollcalls': [rollcall()]}
                        self.assertEqual(handler.process_rollcalls(data, session), data)
                    session.put.assert_called_once()
                    self.assertEqual(session.put.call_args.kwargs['json']['numberCode'], '0026')

    def test_windows_ctrl_p_and_other_keys(self):
        for sequence in ('\x10', '\t', 'p', 'P', '\x1b[Z', '\x00\x0f', '\x00\x10', '\xe0\x10', '\x00\x48'):
            with self.subTest(sequence=repr(sequence)):
                keys = list(sequence)
                console = Mock()
                # kbhit does not report getwch's buffered extended scan code.
                console.kbhit.side_effect = lambda: (
                    len(keys) == len(sequence) if sequence[0] in ('\x00', '\xe0') else bool(keys)
                )
                console.getwch.side_effect = lambda: keys.pop(0)
                with patch.object(tui.sys.stdin, 'isatty', return_value=True), patch.object(
                    tui.os, 'name', 'nt'
                ), patch.dict('sys.modules', msvcrt=console):
                    with tui.submission_shortcut() as wait:
                        self.assertEqual(wait(0), sequence == '\x10')
                        self.assertFalse(wait(0))

    def test_ctrl_c_still_interrupts(self):
        console = Mock()
        console.kbhit.return_value = True
        console.getwch.return_value = '\x03'
        with patch.object(tui.sys.stdin, 'isatty', return_value=True), patch.object(
            tui.os, 'name', 'nt'
        ), patch.dict('sys.modules', msvcrt=console):
            with tui.submission_shortcut() as wait:
                with self.assertRaises(KeyboardInterrupt):
                    wait(5)
