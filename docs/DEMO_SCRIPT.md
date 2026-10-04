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
7. Open Evaluation separately. Explain that saved policy results are provisional
   pending the evaluator corrections in CODE_REVIEW.md.

This demonstration uses real historical Calgary reports and simulated repairs
with a frozen August 24, 2026 planning clock. It does not show field operations.
Use `make reset` only when intentionally clearing previous simulated work.
ElevenLabs agent setup and its live call demonstration are still outstanding.
