# CareerVault — Initial Reference Notes

> Captured from the initial scoping conversation. These are **draft proposals**
> from before requirements were formalized — expect them to evolve once the
> requirements document is finalized.

---

## Proposed phased build plan (draft)

**Phase 1 — Foundation (Week 1–2)**
- AWS SAM project scaffold
- DynamoDB table + schema
- Cognito user pool
- `career_crud` Lambda (create/read/update career entries)
- API Gateway routes
- Basic React dashboard + milestone input form

**Phase 2 — Core tracking UI (Week 3–4)**
- Career timeline view
- Category tagging (milestone types)
- Goal tracking
- Profile/resume base setup wizard

**Phase 3 — Notifications (Week 5–6)**
- EventBridge cron rule (weekly / monthly)
- `checkin_lambda` — sends a personalised SES email asking for new milestones
- Email deep-link back to the "Add Milestone" page

**Phase 4 — AI features (Week 7–8)**
- Bedrock integration via `bedrock_client.py`
- `resume_gen` Lambda — takes career history + job description, returns tailored resume
- Resume preview in the UI
- `ai_planner` Lambda — cert study plan, career path suggestions

**Phase 5 — Outputs (Week 9–10)**
- PDF resume export (use `weasyprint` or `reportlab` in Lambda)
- HTML portfolio page generator (S3-hosted static page)
- Business card template export

---

## Proposed project structure (draft)

```
career-vault/
├── CLAUDE.md                  ← project bible for Claude Code
├── README.md
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── MilestoneForm.jsx
│   │   │   ├── CareerTimeline.jsx
│   │   │   └── ResumeGenerator.jsx
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── AddMilestone.jsx
│   │   │   └── GenerateResume.jsx
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── functions/
│   │   ├── career/
│   │   │   ├── handler.py      ← CRUD for milestones/entries
│   │   │   └── requirements.txt
│   │   ├── resume/
│   │   │   ├── handler.py      ← AI-powered resume tailoring
│   │   │   └── requirements.txt
│   │   ├── planner/
│   │   │   ├── handler.py      ← cert/career planning
│   │   │   └── requirements.txt
│   │   └── checkin/
│   │       ├── handler.py      ← triggered by EventBridge
│   │       └── requirements.txt
│   └── shared/
│       ├── dynamo_client.py
│       ├── bedrock_client.py
│       └── models.py
├── infrastructure/
│   ├── template.yaml           ← SAM template (all AWS resources)
│   └── samconfig.toml
└── docs/
    └── architecture.md
```

---

## Getting-started notes & gotchas

- **Python version**: 3.13 (Lambda supports it since late 2024)
- **AWS CLI auth**: use IAM Identity Center (`aws sso login`) or an IAM user with access keys — never the root account
- **Bedrock model access**: now auto-enabled across commercial regions on first invoke (no more manual approval). IAM role still needs `bedrock:InvokeModel` permissions.
- **SAM vs CDK**: SAM chosen for cleaner Lambda-centric YAML and `sam local start-api` for local testing. CDK reserved for future projects where the imperative style would pay off.
- **SES sandbox**: new AWS accounts can only send to verified addresses. Production access requires a short form — file this around the time notifications get built.
- **Cost guardrails**: set a $5/month AWS Budget alert before deploying anything.
