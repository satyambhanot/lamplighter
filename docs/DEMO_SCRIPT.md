# Lamplighter — Dispatch Demo

1. Run `make configure`, then `make api` and `make dash` in separate terminals.
2. Start in Historical preview. Select a queue row or map pin; inspect priority
   reasons and the partial source-report history. Toggle school and transit layers.
3. Reduce capacity from 100% to 80%. Inspect removed/added tickets, affected
   communities, and allocated hours. Explain that route membership can change.
4. Restore 100%, select Live dispatch, and click Review this plan. Review the
   visit order, acknowledge it, and confirm. Confirmed assignments retain their
   original stop numbers.
5. Select a confirmed light, acknowledge crew completion, and click Mark repaired.
   The light leaves the open queue and appears as completed in the confirmed plan.
6. Show Recent activity. A report arriving after confirmation requires a new plan
   review before another repair can be recorded.
7. Open Evaluation separately and show the FIFO, version 1 and tuned comparison on the
   unseen July to August weeks. Known modelling limits are listed in CODE_REVIEW.md and
   REFACTOR_REVIEW.md.
8. Voice: with `make tunnel` running and Live dispatch selected, start an ElevenLabs test
   call to "Lamplighter street light line" and report a light near King George School.
   The new light appears in the queue and in Recent activity within 5 seconds. A second
   call about the same place merges into it, and Recent activity shows the re-rank.

This demonstration uses real historical Calgary reports and simulated repairs
with a frozen August 24, 2026 planning clock. It does not show field operations.
Use `make reset` only when intentionally clearing previous simulated work.
Voice setup and a fallback (`make voice-test`, or `scripts/fake_call.py` against the
local API) are in voice/SETUP.md.
