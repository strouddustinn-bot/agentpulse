from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-deploy.yml"
GITIGNORE = ROOT / ".gitignore"


class ProductionRecoveryWorkflowTests(unittest.TestCase):
    def test_runtime_failure_state_is_ignored_before_restore_cleanliness_check(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        ignored = {
            line.strip()
            for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertIn("production-failure-state.json", ignored)

        capture = workflow.index('Path("production-failure-state.json").write_text(')
        restore = workflow.index("- name: Restore pre-migration export into disposable D1")
        cleanliness = workflow.index('test -z "$(git status --porcelain)"', restore)

        self.assertLess(capture, restore)
        self.assertLess(restore, cleanliness)
        self.assertIn(
            'printf \'%s\\n\' \'{"disposable_d1_restore":"pass","disposable_d1_deleted":true}\'',
            workflow[cleanliness:],
        )


if __name__ == "__main__":
    unittest.main()
