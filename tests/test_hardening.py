import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from harness import guard
from harness.agent import AgentError, invoke_codex, run_agent, verification_cli
from harness.core import fingerprint, input_files, load_manifest, project_status
from tests import test_agent, test_cli, test_init, test_roles


class BoundaryTests(unittest.TestCase):
    setUp = test_agent.AgentTests.setUp
    save = test_cli.HarnessTests.save
    run_with = test_agent.AgentTests.run_with
    fix = test_agent.AgentTests.fix

    def test_untracked_test_runner_shadow_is_rejected_before_verification(self):
        def change(root, context, *args):
            if context['phase'] == 'implement':
                (root / 'unittest.py').write_text('# bypass tests\n', encoding='utf-8')
            return test_agent.response()
        result, _ = self.run_with(change)
        self.assertEqual(result['reason'], 'scope_changed')
        self.assertIn('unittest.py', result['changed_files'])
        self.assertNotEqual(result['status'], 'passed')

    def test_bytecode_cache_outside_allowed_paths_is_not_a_blind_spot(self):
        def change(root, context, *args):
            cache = root / '__pycache__'
            cache.mkdir()
            (cache / 'test_logic.pyc').write_bytes(b'forged bytecode')
            return test_agent.response()
        result, _ = self.run_with(change)
        self.assertEqual(result['reason'], 'scope_changed')
        self.assertIn('__pycache__/test_logic.pyc', result['changed_files'])

    def test_bytecode_cache_inside_allowed_paths_is_rejected(self):
        package = self.root / 'pkg'
        package.mkdir()
        (package / '__init__.py').write_text('', encoding='utf-8')
        self.manifest['inputs'].append('pkg')
        self.manifest['agent']['code_paths'].append('pkg')
        self.save()
        def change(root, context, *args):
            if context['phase'] == 'implement':
                (root / 'logic.py').write_text('VALUE = 2\n', encoding='utf-8')
                cache = root / 'pkg' / '__pycache__'
                cache.mkdir()
                (cache / '__init__.cpython-313.pyc').write_bytes(b'forged bytecode')
            return test_agent.response()
        result, _ = self.run_with(change)
        self.assertEqual(result['reason'], 'scope_changed')
        self.assertIn('pkg/__pycache__/__init__.cpython-313.pyc', result['changed_files'])
        self.assertNotIn('logic.py', result['changed_files'])

    def test_untracked_existing_file_deletion_is_rejected_even_on_provider_error(self):
        keep = self.root / 'keep.txt'
        keep.write_text('user content', encoding='utf-8')
        def change(*args):
            keep.unlink()
            raise AgentError('agent_exit', 'Provider failed after editing')
        result, _ = self.run_with(change)
        self.assertEqual(result['reason'], 'scope_changed')
        self.assertIn('keep.txt', result['changed_files'])

    def test_forged_evidence_stops_agent_and_invalidates_history(self):
        def change(root, context, *args):
            if context['phase'] == 'implement':
                (root / '.harness' / 'runs' / 'zz-forged.json').write_text(json.dumps({
                    'schema_version': 1, 'run_id': 'zz-forged',
                    'fingerprint': fingerprint(root, self.manifest), 'stable': True,
                    'results': [{'id': 'CHK-1', 'status': 'passed'}],
                }), encoding='utf-8')
            return test_agent.response()
        result, _ = self.run_with(change)
        self.assertEqual(result['reason'], 'evidence_changed')
        self.assertNotEqual(result['status'], 'passed')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            project_status(self.root, self.manifest, fingerprint(self.root, self.manifest))

    def test_deleted_evidence_is_detected_on_failure(self):
        def change(root, *args):
            next((root / '.harness' / 'runs').glob('*.json')).unlink()
            raise AgentError('invalid_response', 'Malformed output')
        result, _ = self.run_with(change)
        self.assertEqual(result['reason'], 'evidence_changed')

    def test_old_green_history_cannot_override_current_red(self):
        runs = self.root / '.harness' / 'runs'
        runs.mkdir(parents=True)
        (runs / 'zz-forged.json').write_text(json.dumps({
            'schema_version': 1, 'run_id': 'zz-forged', 'stable': True,
            'fingerprint': fingerprint(self.root, self.manifest),
            'results': [{'id': 'CHK-1', 'status': 'passed'}],
        }), encoding='utf-8')
        result, agent = self.run_with(lambda *args: test_agent.response())
        self.assertEqual(result['reason'], 'no_progress')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(agent.call_count, 2)

    def test_project_module_does_not_replace_verifier(self):
        (self.root / 'harness.py').write_text(
            'print(\'{"schema_version": 1, "status": "valid", "fake": true}\')\n', encoding='utf-8')
        result = verification_cli(self.root, self.manifest, 'check')
        self.assertNotIn('fake', result)
        self.assertIn('counts', result)

    def test_red_diagnostic_includes_ids_reasons_and_evidence(self):
        result, _ = self.run_with(lambda *args: test_agent.response(red_check_ids=['MISSING']))
        self.assertEqual(result['expected_red_check_ids'], ['MISSING'])
        self.assertEqual(result['observed_red_check_ids'], ['CHK-1'])
        self.assertEqual(result['missing_red_check_ids'], ['MISSING'])
        self.assertTrue((self.root / result['verification_record']).is_file())
        self.assertEqual(result['check_diagnostics'][0]['reason'], 'exit_code')

    def test_sigterm_persists_interruption_and_restores_handler(self):
        previous = signal.getsignal(signal.SIGTERM)
        def stop(*args):
            signal.raise_signal(signal.SIGTERM)
        result, _ = self.run_with(stop)
        self.assertEqual(result['reason'], 'interrupted')
        self.assertEqual(result['signal'], 'SIGTERM')
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_readonly_claude_cannot_add_untracked_file(self):
        self.manifest['agent']['workflow'] = 'claude-codex'
        self.save()
        def change(root, *args):
            (root / 'untracked.txt').write_text('unexpected', encoding='utf-8')
            return test_roles.design()
        with patch('harness.claude.invoke_claude', side_effect=change):
            result, codex = self.run_with(self.fix)
        self.assertEqual(result['reason'], 'scope_changed')
        codex.assert_not_called()


class InitBoundaryTests(unittest.TestCase):
    setUp = test_init.InitTests.setUp
    run_with = test_init.InitTests.run_with

    def test_untracked_scaffold_file_is_rejected(self):
        def scaffold(root, context, directory, timeout):
            result = test_init.scaffold(root, context, directory, timeout)
            (root / 'unittest.py').write_text('# bypass tests', encoding='utf-8')
            return result
        result, _, _ = self.run_with(codex=scaffold)
        self.assertEqual(result['reason'], 'scope_changed')
        self.assertIn('unittest.py', result['changed_files'])
        self.assertFalse((self.root / 'harness.json').exists())

    def test_init_protects_outer_evidence(self):
        def scaffold(root, context, directory, timeout):
            result = test_init.scaffold(root, context, directory, timeout)
            (root.parent / 'run.json').write_text('{}', encoding='utf-8')
            return result
        result, _, _ = self.run_with(codex=scaffold)
        self.assertEqual(result['reason'], 'evidence_changed')
        self.assertFalse((self.root / 'harness.json').exists())

    def test_init_protects_draft_run_history_too(self):
        def scaffold(root, context, directory, timeout):
            result = test_init.scaffold(root, context, directory, timeout)
            history = root / '.harness' / 'runs'
            history.mkdir(parents=True)
            (history / 'forged.json').write_text('{}', encoding='utf-8')
            return result
        result, _, _ = self.run_with(codex=scaffold)
        self.assertEqual(result['reason'], 'evidence_changed')
        self.assertFalse((self.root / 'harness.json').exists())

    def test_scaffold_red_diagnostic_reports_invalid_execution(self):
        def scaffold(root, context, directory, timeout):
            result = test_init.scaffold(root, context, directory, timeout)
            (root / 'tests' / 'test_scenario_001.py').write_text('# no tests', encoding='utf-8')
            return result
        result, _, _ = self.run_with(codex=scaffold)
        self.assertEqual(result['expected_red_check_ids'], ['CHK-001'])
        self.assertEqual(result['observed_red_check_ids'], [])
        self.assertEqual(result['missing_red_check_ids'], ['CHK-001'])
        self.assertTrue((self.root / result['verification_record']).exists())


class RepairTests(unittest.TestCase):
    setUp = test_agent.CodexAdapterTests.setUp
    save = test_cli.HarnessTests.save

    def test_codex_repairs_only_response_once_with_readonly_sandbox(self):
        outputs = ['not JSON', json.dumps(test_agent.response())]
        processes = [Mock(returncode=0), Mock(returncode=0)]
        for process, output in zip(processes, outputs):
            process.communicate.return_value = (output, '')
        with patch('harness.agent.shutil.which', return_value='codex'), \
                patch('harness.agent.subprocess.Popen', side_effect=processes) as launch:
            result = invoke_codex(self.root, self.context, self.directory, 30)
        self.assertEqual(result, test_agent.response())
        self.assertEqual(launch.call_count, 2)
        command = launch.call_args.args[0]
        self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
        repair_prompt = processes[1].communicate.call_args.kwargs['input']
        self.assertIn('not JSON', repair_prompt)
        self.assertNotIn('Work on exactly the supplied requirement', repair_prompt)
        self.assertTrue((self.directory / 'repair' / 'stdout.log').exists())
        self.assertEqual((self.directory / 'stdout.log').read_text(encoding='utf-8'), 'not JSON')

    def test_second_malformed_response_is_final(self):
        process = Mock(returncode=0)
        process.communicate.return_value = ('bad JSON', '')
        with patch('harness.agent.shutil.which', return_value='codex'), \
                patch('harness.agent.subprocess.Popen', return_value=process) as launch:
            with self.assertRaises(AgentError) as error:
                invoke_codex(self.root, self.context, self.directory, 30)
        self.assertEqual(error.exception.reason, 'invalid_response')
        self.assertEqual(launch.call_count, 2)

    def test_repair_cannot_edit_code(self):
        processes = [Mock(returncode=0), Mock(returncode=0)]
        processes[0].communicate.return_value = ('bad JSON', '')
        def mutate(**kwargs):
            (self.root / 'logic.py').write_text('VALUE = 999\n', encoding='utf-8')
            return json.dumps(test_agent.response()), ''
        processes[1].communicate.side_effect = mutate
        with patch('harness.agent.shutil.which', return_value='codex'), \
                patch('harness.agent.subprocess.Popen', side_effect=processes):
            with self.assertRaises(AgentError) as error:
                invoke_codex(self.root, self.context, self.directory, 30)
        self.assertEqual(error.exception.reason, 'scope_changed')

    def test_claude_repairs_without_tools(self):
        from harness.claude import invoke_claude
        processes = [Mock(returncode=0), Mock(returncode=0)]
        for process, value in zip(processes, [{}, test_roles.design()]):
            process.communicate.return_value = (json.dumps({
                'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': value}), '')
        with patch('harness.claude.shutil.which', return_value='claude'), \
                patch('harness.agent.subprocess.Popen', side_effect=processes) as launch:
            result = invoke_claude(self.root, {'phase': 'design'}, self.directory, 30)
        self.assertEqual(result, test_roles.design())
        command = launch.call_args.args[0]
        self.assertEqual(command[command.index('--tools') + 1], '')

    def test_interrupt_terminates_child_tree(self):
        process = Mock(returncode=0)
        process.communicate.side_effect = KeyboardInterrupt
        with patch('harness.agent.shutil.which', return_value='codex'), \
                patch('harness.agent.subprocess.Popen', return_value=process), \
                patch('harness.agent.terminate_tree') as terminate:
            with self.assertRaises(KeyboardInterrupt):
                invoke_codex(self.root, self.context, self.directory, 30)
        terminate.assert_called_once_with(process)


class DoctorTests(unittest.TestCase):
    setUp = test_cli.HarnessTests.setUp
    save = test_cli.HarnessTests.save

    def test_doctor_checks_auth_without_exposing_account_data(self):
        from harness.doctor import run_doctor
        def execute(command, **kwargs):
            if command[-1] == '--version':
                output = 'codex-cli 0.160.1' if command[0] == 'codex' else '2.1.241 (Claude Code)'
            elif command[0] == 'claude':
                output = json.dumps({'loggedIn': True, 'email': 'private@example.test', 'apiKey': 'secret'})
            else:
                output = 'Logged in using ChatGPT'
            return subprocess.CompletedProcess(command, 0, output, '')
        with patch('harness.doctor.shutil.which', side_effect=lambda value: value), \
                patch('harness.doctor.subprocess.run', side_effect=execute) as run:
            result = run_doctor(self.root)
        self.assertEqual(result['status'], 'ready')
        self.assertNotIn('private@example.test', json.dumps(result))
        self.assertNotIn('secret', json.dumps(result))
        self.assertFalse(any('exec' in call.args[0] or '--print' in call.args[0] for call in run.call_args_list))

    def test_missing_cli_is_actionable_and_does_not_require_manifest(self):
        from harness.doctor import run_doctor
        (self.root / 'harness.json').unlink()
        with patch('harness.doctor.shutil.which', return_value=None):
            result = run_doctor(self.root)
        self.assertEqual(result['status'], 'needs_input')
        missing = [item for item in result['checks'] if item.get('reason') == 'missing_cli']
        self.assertEqual(len(missing), 2)
        self.assertTrue(all(item['action'] for item in missing))

    def test_auth_failure_and_timeout_are_distinct(self):
        from harness.doctor import run_doctor
        def execute(command, **kwargs):
            if command[-1] == '--version':
                return subprocess.CompletedProcess(command, 0, '1.0', '')
            if command[0] == 'codex':
                raise subprocess.TimeoutExpired(command, 10)
            return subprocess.CompletedProcess(command, 1, '{"loggedIn": false}', '')
        with patch('harness.doctor.shutil.which', side_effect=lambda value: value), \
                patch('harness.doctor.subprocess.run', side_effect=execute):
            result = run_doctor(self.root)
        self.assertEqual(result['status'], 'needs_input')
        self.assertEqual({item['reason'] for item in result['checks'] if item['status'] != 'passed'},
                         {'timeout', 'not_authenticated'})


class ProviderPreflightTests(unittest.TestCase):
    setUp = test_agent.AgentTests.setUp
    save = test_cli.HarnessTests.save

    def test_missing_provider_stops_before_verification_and_model_calls(self):
        self.manifest['agent']['workflow'] = 'claude-codex'
        self.save()
        with patch('harness.agent.shutil.which', side_effect=lambda name: None if name == 'codex' else name), \
                patch('harness.agent.verification_cli') as verifier, \
                patch('harness.claude.invoke_claude') as claude:
            result = run_agent(self.root, self.manifest)
        self.assertEqual((result['status'], result['reason'], result['missing']), ('error', 'agent_missing', ['codex']))
        self.assertIn('codex login', result['message'])
        self.assertEqual(result['phases'], [])
        verifier.assert_not_called()
        claude.assert_not_called()

    def test_init_checks_both_providers_before_paying_for_a_spec(self):
        from harness.spec import run_init
        project = self.root / 'new'
        brief = self.root / 'brief.txt'
        brief.write_text('Return 2', encoding='utf-8')
        with patch('harness.agent.shutil.which', return_value=None), \
                patch('harness.spec.invoke_claude') as claude:
            result = run_init(project, brief)
        self.assertEqual((result['reason'], result['missing']), ('agent_missing', ['claude', 'codex']))
        claude.assert_not_called()
        self.assertEqual([p.name for p in (project / result['draft']).iterdir()], ['BRIEF.md'])


class SnapshotTests(unittest.TestCase):
    """Digests are reused only for settled files whose stat signature did not change."""
    save = test_cli.HarnessTests.save

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.file = self.root / 'data.txt'
        self.file.write_text('aaaa', encoding='utf-8')
        cache = patch.dict(guard._digests, clear=True)
        cache.start()
        self.addCleanup(cache.stop)

    def settled(self):
        """Pretend an hour has passed, so current files are outside the settle window."""
        return patch('harness.guard.time.time_ns', return_value=time.time_ns() + 3_600_000_000_000)

    def hash_count(self):
        with patch('harness.guard.hashlib.file_digest', wraps=hashlib.file_digest) as digest:
            tree_snapshot = guard.tree_snapshot(self.root)
        return digest.call_count, tree_snapshot

    def test_unchanged_settled_file_is_not_hashed_again(self):
        with self.settled():
            self.assertEqual(self.hash_count()[0], 1)
            count, snapshot = self.hash_count()
        self.assertEqual(count, 0)
        self.assertEqual(snapshot['data.txt'], hashlib.sha256(b'aaaa').hexdigest())

    def test_recently_written_file_is_hashed_every_time(self):
        self.assertEqual(self.hash_count()[0], 1)
        self.assertEqual(self.hash_count()[0], 1)

    def test_same_size_rewrite_is_detected_after_reuse(self):
        with self.settled():
            before = guard.tree_snapshot(self.root)
        self.file.write_text('bbbb', encoding='utf-8')
        self.assertEqual(guard.changed_paths(before, guard.tree_snapshot(self.root)), ['data.txt'])

    @unittest.skipIf(os.name == 'nt', 'Windows has no inode change time; SPEC documents this limit')
    def test_rewrite_with_restored_timestamps_is_detected_on_posix(self):
        original = self.file.stat()
        with self.settled():
            before = guard.tree_snapshot(self.root)
            self.file.write_text('bbbb', encoding='utf-8')
            os.utime(self.file, ns=(original.st_atime_ns, original.st_mtime_ns))
            self.assertEqual(self.file.stat().st_mtime_ns, original.st_mtime_ns)
            after = guard.tree_snapshot(self.root)
        self.assertEqual(guard.changed_paths(before, after), ['data.txt'])

    def test_streamed_fingerprint_keeps_existing_records_valid(self):
        test_cli.HarnessTests.setUp(self)
        manifest = load_manifest(self.root)
        expected = hashlib.sha256()
        for path in input_files(self.root, manifest):
            expected.update(path.relative_to(self.root).as_posix().encode('utf-8') + b'\0')
            expected.update(hashlib.sha256(path.read_bytes()).digest())
        self.assertEqual(fingerprint(self.root, manifest), expected.hexdigest())


class ExecutionBoundaryTests(unittest.TestCase):
    setUp = test_cli.HarnessTests.setUp
    save = test_cli.HarnessTests.save
    cli = test_cli.HarnessTests.cli

    def test_checks_cannot_forge_history(self):
        self.manifest['checks'][0]['command'] = [
            '{python}', '-c',
            "from pathlib import Path; p=Path('.harness/runs'); p.mkdir(parents=True,exist_ok=True); (p/'zz.json').write_text('{}')",
        ]
        self.save()
        result = self.cli('run', expected=2)
        self.assertEqual(result['reason'], 'evidence_changed')
        self.assertFalse(result['stable'])
        self.assertIn('integrity', self.cli('status', expected=2)['error'])

    def test_sigterm_during_checks_saves_failed_interrupted_result(self):
        from harness.core import run_checks
        def stop(*args):
            signal.raise_signal(signal.SIGTERM)
        with patch('harness.core.execute_check', side_effect=stop):
            result = run_checks(self.root, self.manifest, fingerprint(self.root, self.manifest))
        self.assertEqual(result['status'], 'needs_input')
        self.assertEqual(result['signal'], 'SIGTERM')
        self.assertEqual(result['results'][0]['reason'], 'interrupted')
        self.assertFalse(result['stable'])
        self.assertEqual(json.loads((self.root / '.harness' / 'runs' / (result['run_id'] + '.json')).read_text(encoding='utf-8')), result)

    def test_verifier_ignores_project_sitecustomize_from_pythonpath(self):
        import os
        (self.root / 'sitecustomize.py').write_text(
            "import os; print('project startup injection', flush=True); os._exit(0)", encoding='utf-8')
        with patch.dict(os.environ, {'PYTHONPATH': str(self.root)}):
            result = verification_cli(self.root, self.manifest, 'check')
        self.assertEqual(result['status'], 'valid')
        self.assertIn('counts', result)

    def test_public_doctor_does_not_load_required_manifest(self):
        from harness.__main__ import main
        with patch('sys.argv', ['harness', '--root', str(self.root), 'doctor', '--provider', 'codex']), \
                patch('harness.__main__.run_doctor', return_value={'status': 'ready'}) as doctor, \
                patch('harness.__main__.load_manifest', side_effect=AssertionError('No required contract')), \
                patch('builtins.print'):
            self.assertEqual(main(), 0)
        doctor.assert_called_once_with(self.root, 'codex')

    def test_verifier_timeout_cleans_up_process_tree(self):
        from harness.processes import run_command
        process = Mock(returncode=1)
        process.communicate.side_effect = [subprocess.TimeoutExpired('verify', 1), ('partial log', '')]
        with patch('harness.processes.subprocess.Popen', return_value=process), \
                patch('harness.processes.terminate_tree') as terminate:
            with self.assertRaises(subprocess.TimeoutExpired) as error:
                run_command(['verify'], timeout=1)
        self.assertEqual(error.exception.output, 'partial log')
        terminate.assert_called_once_with(process)


if __name__ == '__main__':
    unittest.main()
