# Sample call transcript

A real ElevenLabs browser test call to the "Lamplighter street light line" agent on Saturday, October 3, 2026 at 20:16 MDT (conversation `conv_0701m42b5051ej8bq7hd2ptmb7s1`, 72 seconds). The API ran on the team laptop behind the ngrok tunnel, with the demo clock frozen at Monday, August 24, 2026. Speech-to-text fragments are kept as recorded.

| Time | Speaker | What was said |
|---|---|---|
| 0 s | Agent | Hi, this is Lamplighter, Calgary's street light line. Are you reporting a light that's out, or checking on one you already reported? |
| 10 s | Caller | Um, I, I want to report the light. |
| 15 s | Agent | No problem, I can help with that. Could you tell me where the light is? The nearest street address, intersection, or landmark works. |
| 24 s | Caller | There's a streetlight. |
| 26 s | Caller | Out. |
| 28 s | Agent | I need the specific location to file your report, such as a street address or intersection. Could you please tell me where the light is located? |
| 37 s | Caller | Yes, it's the street light out near King George School. |
| 41 s | Agent | Let me confirm, the street light out is near King George School. Is that correct? |
| 47 s | Caller | Yes, that's right. |
| 48 s | Agent | Is the pole down, or can you see any exposed wires or sparking? |
| 54 s | Caller | Um, the pole is standing. |
| 57 s | Agent | Your report has been filed and is currently number ten in the repair queue. A crew should fix it the week of September first. |
| 66 s | Caller | Thank you. Bye-bye. |
| 67 s | Agent | You're welcome, have a great day! Goodbye. |

## Tool call

After the caller confirmed the location and answered the safety question, the agent called `report_light`. ElevenLabs added the fixed demo phone number and the voice key header.

```text
POST https://<NGROK_DOMAIN>/report
{"phone": "+14035550100", "location_text": "King George School", "description": "The street light is out near King George School."}
```

The API answered in 0.33 seconds:

```json
{"ticket_id": "L-a5c7dc1f872f", "merged": false, "hazard": false, "needs_clarification": false, "rank": 10, "old_rank": null, "expected_fix_date": "2026-09-01", "message": "New report entered at priority #10."}
```

The API logged the event "New report entered at priority #10." The light appeared in the dashboard's Live dispatch view as rank 10, with the reasons "near a school, near transit, 0.0 weeks old".

## What this shows

- The agent read the address back and asked about a downed pole or wires before filing, as required.
- The caller was never asked for a phone number.
- The rank and the repair week came from the API's answer, not from the model.
