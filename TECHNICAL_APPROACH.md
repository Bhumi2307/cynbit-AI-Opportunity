# Technical approach: support-ticket triage copilot

## Demo scope and status

This proof of concept adds `POST /api/ai/triage` to the existing Flask application. It proposes an issue category, priority, and support team from a natural-language ticket description, returns raw (uncalibrated) model scores and a neutral response draft, and flags lower-scoring predictions for review. It **never** writes a ticket, changes an SLA, or sends a response. Existing ticket endpoints and processing behavior are unchanged.

The included classifier trains at process startup on a small, hand-authored **synthetic** example set. This makes the demo runnable without private data, API keys, model downloads, or a hosted LLM. It does not establish production accuracy or generalize reliably to real-world traffic.

## Model choices

- **Issue type:** multinomial logistic regression over TF-IDF word unigrams and bigrams.
- **Priority:** a second TF-IDF/logistic-regression classifier over the same description, with balanced class weights. Explicit high-risk phrases (e.g., a security breach, data loss, or production outage) override its priority suggestion to `high`; this is a deliberately narrow demo safeguard, not a complete incident detector.
- **Routing:** reuses the existing `TicketAutomation.routing_map`; the model does not invent team names.
- **Scores and review:** return per-field class probabilities (raw, uncalibrated demo scores). A prediction is flagged for human review if either score is below the provisional 0.60 threshold. All predictions still require a human decision: `auto_action` is always `false`. Calibrate a threshold against held-out, representative data before using it operationally.
- **Response draft:** deterministic template using only the proposed category and team. No generative model is used; the text does not claim a fix or promise a resolution.

TF-IDF and logistic regression are intentionally lightweight, inspectable, and fast to retrain for a baseline. For production, compare them with stronger baselines only after obtaining authorized, labeled data. A larger language model is not required to validate this triage hypothesis.

## Data and inference pipeline

1. Receive JSON with a `Description` (or `description`) string. Reject missing, blank, non-string, or over-4,000-character input.
2. Normalize leading/trailing whitespace; transform text using the same fitted TF-IDF vectorizers.
3. Predict issue type and priority; apply the limited high-urgency phrase override.
4. Map the predicted category to the existing team map.
5. Return structured suggestions, confidence, review flag, model version, decision basis, and a template acknowledgement.
6. Do not persist the request or output in this endpoint. The caller must obtain human approval before using the existing ticket submission workflow.

The demo examples contain no real users or customer records. A production pipeline should use only authorized, purpose-limited tickets; redact names, email addresses, secrets, and unrelated personal data; preserve labels with provenance and annotator agreement; partition train/validation/test sets by time (and, where appropriate, customer); and prevent duplicate/near-duplicate leakage. Keep a separate severe-incident evaluation slice.

## API example

Run `python app.py`, then send:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:5000/api/ai/triage `
  -ContentType 'application/json' `
  -Body '{"Description":"All employees have lost network access during the customer launch"}'
```

The JSON response includes:

```json
{
  "suggested_issue_type": "wifi",
  "suggested_priority": "high",
  "suggested_team": "Network",
  "confidence": {"issue_type": 0.3613, "priority": 0.5314},
  "human_review_required": true,
  "auto_action": false,
  "decision_basis": "urgent_signal_override",
  "model_version": "synthetic-demo-v1",
  "response_draft": "Thanks for reporting this. We suggest categorizing it as wifi and routing it to Network. A support specialist will review the details and follow up."
}
```

This is the observed response for the included synthetic-demo model version, not a measured accuracy claim. Scores are raw and uncalibrated; the urgent-signal override sets the priority to `high` independently of the model's priority ranking. Low scores should trigger review, never a silent fallback.

## Prompt and LLM architecture

There is no prompt and no LLM call in this POC. Classification is a local supervised model and the acknowledgement is a fixed template. This avoids sending ticket data to a third party and avoids unsupported resolution instructions. If a later product experiment adds retrieval or generation, use only approved knowledge sources, attach citations to suggested answers, isolate retrieved content from system instructions, treat ticket text as untrusted input, and require agent review. Do not place an LLM in the critical priority path until it passes a separate safety evaluation.

## Validation plan and acceptance gates

The included tests exercise the Flask endpoint's category/team suggestion, urgent override, invalid/oversized input handling, JSON response shape, and no-auto-action guard. Run:

```powershell
python -m unittest discover -s tests -v
```

Before any pilot, replace synthetic examples with an approved labeled corpus and evaluate on an untouched, representative, time-separated set. Report per-class precision/recall/F1, calibration, urgent-case recall, subgroup results where lawful and meaningful, and suggestion coverage. Compare to current routing and a simple majority-class baseline. Agree thresholds with support owners; do not infer production readiness from passing unit tests.

## Execution plan

| Phase | Work | Exit criteria |
|---|---|---|
| 0. Discovery (1 week) | Confirm workflow, labels, severity definitions, volumes, integrations, data rights, and baseline effort/SLA metrics with Cynbit and a design partner. | Approved scope, owner, data map, baseline, and acceptance thresholds. |
| 1. Dataset/evaluation (1–2 weeks) | Sample and redact tickets; label category/priority; measure agreement; build temporal holdout and incident slice. | Data authorization documented; label quality and evaluation protocol approved. |
| 2. Shadow pilot (2–4 weeks) | Deploy behind authentication in an isolated environment; log versioned predictions/agent corrections with minimum retention; do not alter tickets. | Quality gates met; no material privacy/security issue; review and override UX validated. |
| 3. Agent assist (2–4 weeks) | Enable opt-in suggestions, explicit accept/edit/reject actions, and audit trail; retain manual workflow and rollback. | Improved measured triage effort without degraded urgent recall, fairness, or SLA outcomes. |
| 4. Scale/maintain (ongoing) | Integrate approved helpdesk systems; monitor drift, overrides, latency, quality, cost, and incident signals; revalidate each model release. | Named operational owner, rollback path, change controls, and periodic review. |

## Operational requirements for production

- Authentication, authorization, rate limiting, request limits, input sanitization, and audit records without storing unnecessary ticket text.
- Secrets and environment-specific configuration outside source control; encrypted transport and encrypted storage if persistence is introduced.
- Versioned model/data/label schemas; reproducible training; rollback; documented retention and deletion.
- Monitoring for latency, unavailable model, class mix, confidence, correction rate, per-class quality, drift, cost, and privacy/security events.
- A support-agent interface with editable fields, uncertainty explanations, and a clear manual route.
- Privacy, security, accessibility, fairness, and applicable legal review before processing customer information.

## Dependencies and limitations

The prototype uses the repository's Flask app plus pandas (already used by the ticket workflow) and scikit-learn. Install the pinned/ranged project dependencies with `pip install -r requirements.txt`. It is a synchronous in-process model; no queue, hosted inference, persisted model artifact, production authentication, UI, or LLM is included.
