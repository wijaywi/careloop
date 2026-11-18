# CareLoop web

Offline-first React + TypeScript + Vite frontend for the CareLoop screening-to-care demo. The application has no API, external asset, or runtime network dependency: all records are seeded synthetic data held in React state.

## Requirements

- Node.js 20 (the repository pins this in `.nvmrc`)
- npm 10+

## Setup and run

Start the synthetic API from the repository root in one terminal:

```bash
python -m api --host 127.0.0.1 --port 8000
```

Then, from this directory, start the frontend in a second terminal:

```bash
npm install
npm run dev
```

Open the local URL printed by Vite. For a production preview:

```bash
npm run build
npm run preview
```

The offline verification command is:

```bash
npm test
```

`npm test` runs the TypeScript project check. `npm run build` runs the same check and creates the deployable `dist/` directory. Deploy the contents of `dist/` to any static host, or serve it with `npm run preview` for a local check.

## Demo walkthrough

1. Select a role from the header or the **Viewing as** selector: navigator, clinician, program manager, or patient.
2. Click **Load demo data** in the blue banner. This resets the seeded case to `CL-2048` in the stalled state and opens Case detail.
3. Progress the human-reviewed flow with **Escalate case**, **Send warm handoff**, and **Close the loop**. The command center journey and case timeline update in local state.
4. Open **Patient view** to read the English result passport, request a local appointment, and record a teach-back response for staff review.
5. Use **Simulation lab** and **Governance** to inspect current transport-ledger outputs, ablations, queue policy, and human-review controls.

The blue demo banner marks synthetic data. The green governance banner marks the human review requirement. No patient or production data is used.

The frontend calls the API through `/api` during Vite development. If the API
is unavailable, the demo remains usable with a clearly labelled local
synthetic fallback. Set `VITE_API_BASE_URL` using `.env.example` when the API
is hosted separately.

All active UI copy is English. Multilingual patient-message templates are
structured in the API with native-speaker and clinical-review flags; they are
not presented as approved translations by this frontend.
