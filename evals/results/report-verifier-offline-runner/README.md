# Initial scripted CLI attempt

No model ran. The scripted driver reads evaluator labels to fabricate responses for
runner tests, so these are not semantic evaluation results.

Preparation and replay exited successfully. Scoring wrote score/score.json, then
its status printer raised `TypeError: object of type 'int' has no len()` by treating
the numeric eligible count as a list. The original runner snapshot is runner.py.txt;
the failing CLI regression is preserved in cli-failure.txt. Existing artifacts were
not rewritten after the fix.

The corrected, successfully executed exercise lives in the sibling directory
report-verifier-offline-runner-verified. Current code intentionally refuses this
older preparation because its implementation hash changed.
