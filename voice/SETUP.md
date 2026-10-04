# Voice agent setup

The Lamplighter voice line is an ElevenLabs agent with two webhook tools:

| Tool | Calls | Purpose |
|---|---|---|
| `report_light` | `POST /report` | file a report, or merge it into a nearby open light |
| `check_status` | `GET /status` | read back the most recent report from this line |

ElevenLabs reaches the laptop through an ngrok tunnel on a fixed domain. Both tools send the `X-Lamplighter-Voice-Secret` header from an ElevenLabs workspace secret, so the key never appears in a tool definition. The caller is never asked for a phone number: both tools send the fixed demo number `+14035550100`, so `check_status` returns the latest report from any demo call.

Files:

- `system_prompt.md`: the agent's instructions (read the address back, always ask about downed poles or wires, two sentences per turn, "the week of" dates).
- `tools.json`: both tool definitions, with `{PUBLIC_URL}` and `{VOICE_SECRET_ID}` placeholders.
- `setup_agent.py`: creates or updates the secret, tools and agent (`make voice`).
- `test_call.py`: text-only test call through ElevenLabs (`make voice-test`).

## One-time setup

1. **ElevenLabs key.** In ElevenLabs, open Developers, then API Keys, and create a key with ElevenAgents access. Add it to `.env`:

   ```text
   ELEVENLABS_API_KEY=your-key
   ```

2. **ngrok.** Install it and add your authtoken (Getting Started, then Your Authtoken in the ngrok dashboard):

   ```bash
   brew install ngrok
   ```

   ```bash
   ngrok config add-authtoken your-token
   ```

3. **Fixed domain.** Every free ngrok account has one fixed domain, listed under Domains in the dashboard. Add the host name, without `https://`, to `.env`:

   ```text
   NGROK_DOMAIN=your-name.ngrok-free.app
   ```

4. **Local keys.** If you have not already:

   ```bash
   make configure
   ```

## Every demo session

Run each in its own terminal:

```bash
make api
```

```bash
make tunnel
```

```bash
make dash
```

Then create or update the agent. The first run creates it and saves its IDs to `.env`; later runs update the same agent:

```bash
make voice
```

`make voice` checks that `https://$NGROK_DOMAIN/health` answers before changing anything. Re-run it whenever you edit `system_prompt.md` or `tools.json`.

## Test it

**Text-only test** (uses credits; takes up to a minute):

```bash
make voice-test SCENARIO=report
```

`SCENARIO` is `report`, `status` or `hazard`. The output shows each spoken turn, each tool call and each API result. A `report` test adds a light, so it appears in the dashboard's Live dispatch view.

**Browser call:** open ElevenLabs, go to Agents, open "Lamplighter street light line", and use the test call button. Allow the microphone. Say, for example: "There's a street light out near King George School."

Places that resolve instantly are in `DEMO_ADDRESSES` in `config.py`. Any other Calgary address goes to Nominatim.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `make voice` says `Missing in .env` | Add the named keys, then re-run |
| `make voice` cannot reach `/health` | Start `make api` and `make tunnel` first |
| Tool result is a 401 | Run `make voice` again so the ElevenLabs secret matches `VOICE_SHARED_SECRET` |
| The agent says it cannot find the location | Use a place from `DEMO_ADDRESSES` or a full street address |
| ngrok says the domain is in use | Another `make tunnel` is already running; stop it |
