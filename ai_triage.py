"""Local, human-in-the-loop ticket triage prototype."""

from typing import Mapping

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


_TRAINING_EXAMPLES = [
    ("wifi disconnects every few minutes in the meeting room", "wifi", "medium"),
    ("wireless network is unavailable on my laptop", "wifi", "medium"),
    ("cannot connect to the office wifi after changing my password", "wifi", "low"),
    ("wifi is very slow for everyone on the third floor", "wifi", "high"),
    ("internet access drops whenever I join a video call", "wifi", "medium"),
    ("the guest wireless network says unable to obtain an address", "wifi", "low"),
    ("all employees have lost network access during the customer launch", "wifi", "high"),
    ("network connection is intermittent in the conference room", "wifi", "medium"),
    ("need the guest wifi password for a visitor tomorrow", "wifi", "low"),
    ("complete office network outage, no one can reach production", "wifi", "high"),
    ("I am locked out of my account and cannot sign in", "login", "medium"),
    ("forgot my password for the employee portal", "login", "low"),
    ("multi factor code is rejected when signing in", "login", "medium"),
    ("all staff cannot log in to the payroll system before today's run", "login", "high"),
    ("please unlock my account after too many attempts", "login", "low"),
    ("single sign on redirects me back to the login screen", "login", "medium"),
    ("administrator accounts are locked across the company", "login", "high"),
    ("I need access restored to my account before the client demo", "login", "high"),
    ("my password reset email has not arrived yet", "login", "low"),
    ("cannot authenticate to the production console for any user", "login", "high"),
    ("the desktop application crashes whenever I open a report", "software", "medium"),
    ("a bug in the latest release prevents invoice export", "software", "high"),
    ("please install the approved design application on my workstation", "software", "low"),
    ("the mobile app is slow but still usable", "software", "low"),
    ("the production application is down for every customer", "software", "high"),
    ("I see an error when saving changes in the project tool", "software", "medium"),
    ("the browser extension stopped working after the update", "software", "low"),
    ("our checkout software fails during live transactions", "software", "high"),
    ("the spreadsheet plugin freezes when opening large files", "software", "medium"),
    ("requesting access to the new analytics application", "software", "low"),
    ("laptop screen flickers and keyboard is not responding", "hardware", "medium"),
    ("my workstation will not power on before an important presentation", "hardware", "high"),
    ("request a replacement mouse for my desk", "hardware", "low"),
    ("the office printer is jammed and multiple teams need it", "hardware", "medium"),
    ("server storage device failed and production data may be at risk", "hardware", "high"),
    ("headset microphone is intermittent during calls", "hardware", "low"),
    ("my monitor has a broken display and I cannot work", "hardware", "high"),
    ("laptop battery no longer holds a charge", "hardware", "medium"),
    ("please order a keyboard for a new team member", "hardware", "low"),
    ("core server hardware failure has taken the service offline", "hardware", "high"),
    ("how do I update my profile display name", "other", "low"),
    ("please add a new contractor to the building visitor list", "other", "low"),
    ("I have a question about the expense reimbursement process", "other", "medium"),
    ("urgent, a security breach may have exposed customer records", "other", "high"),
    ("need help finding the company holiday calendar", "other", "low"),
    ("a suspected phishing email was sent to the finance team", "other", "high"),
    ("please update the shipping address on my equipment request", "other", "low"),
    ("I need guidance on the new data retention policy", "other", "medium"),
    ("possible data loss after an unexpected service interruption", "other", "high"),
    ("can someone explain the new travel approval process", "other", "medium"),
]

_URGENT_SIGNALS = (
    "security breach",
    "data breach",
    "data loss",
    "production outage",
    "complete outage",
    "all employees have lost",
    "all staff cannot log in",
    "unavailable for everyone",
    "lost access for everyone",
    "production is down for every customer",
    "everyone is unable",
    "cannot reach production",
)


class TriageAssistant:
    """Suggest ticket category and urgency from synthetic, local training examples."""

    model_version = "synthetic-demo-v1"

    def __init__(self, routing_map: Mapping[str, str]) -> None:
        self._routing_map = dict(routing_map)
        self._category_model = self._new_model()
        self._priority_model = self._new_model()
        descriptions = [row[0] for row in _TRAINING_EXAMPLES]
        self._category_model.fit(descriptions, [row[1] for row in _TRAINING_EXAMPLES])
        self._priority_model.fit(descriptions, [row[2] for row in _TRAINING_EXAMPLES])

    @staticmethod
    def _new_model() -> Pipeline:
        return Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=0)),
            ]
        )

    def predict(self, description: str) -> dict:
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Description must be a non-empty string.")
        if len(description) > 4000:
            raise ValueError("Description must be 4000 characters or fewer.")

        text = description.strip()
        category_probabilities = self._category_model.predict_proba([text])[0]
        category_model = self._category_model.named_steps["classifier"]
        category_index = int(category_probabilities.argmax())
        category = str(category_model.classes_[category_index])

        priority_probabilities = self._priority_model.predict_proba([text])[0]
        priority_model = self._priority_model.named_steps["classifier"]
        priority_index = int(priority_probabilities.argmax())
        priority = str(priority_model.classes_[priority_index])
        decision_basis = "tfidf_logistic_regression"

        normalized_text = text.casefold()
        if any(signal in normalized_text for signal in _URGENT_SIGNALS):
            priority = "high"
            high_index = list(priority_model.classes_).index("high")
            priority_confidence = float(priority_probabilities[high_index])
            decision_basis = "urgent_signal_override"
        else:
            priority_confidence = float(priority_probabilities[priority_index])

        category_confidence = float(category_probabilities[category_index])
        team = self._routing_map.get(category)
        if team is None:
            raise ValueError(f"No support team is configured for category '{category}'.")

        return {
            "suggested_issue_type": category,
            "suggested_priority": priority,
            "suggested_team": team,
            "confidence": {
                "issue_type": round(category_confidence, 4),
                "priority": round(priority_confidence, 4),
            },
            "human_review_required": min(category_confidence, priority_confidence) < 0.60,
            "auto_action": False,
            "decision_basis": decision_basis,
            "model_version": self.model_version,
            "response_draft": (
                f"Thanks for reporting this. We suggest categorizing it as {category} "
                f"and routing it to {team}. A support specialist will review the details "
                "and follow up."
            ),
        }
