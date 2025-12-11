# Human Feedback: test-planner-subagent

## Issues

* Some of the tests didn't pass when run by themselves but would pass when run together with the other tests. The AI then ignored that problem and moved on. After it finished I prodded it and it was able to figure out the problem, but it skipped over the issue initially.
* Not all the work got finished. There was still parts of the code calling outdated references. The core was changed, but not all the code was changed to reflect those core changes.

## Strengths

* I really liked that it ran the code review agent again after it made code changes.
