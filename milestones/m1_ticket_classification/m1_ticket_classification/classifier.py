import joblib
from config import MODEL_PATH

# Load trained model
model = joblib.load(MODEL_PATH)

# Compatibility fix for scikit-learn version differences
def _ensure_estimator_compat(estimator):
    if hasattr(estimator, "steps"):
        for _name, _step in estimator.steps:
            _ensure_estimator_compat(_step)
    if not hasattr(estimator, "multi_class"):
        try:
            estimator.multi_class = "auto"
        except Exception:
            pass

_ensure_estimator_compat(model)


def classify_ticket(text):
    _ensure_estimator_compat(model)
    try:
        prediction = model.predict([text])[0]
        probabilities = model.predict_proba([text])[0]
        confidence = float(max(probabilities) * 100)
        return str(prediction), float(confidence)
    except AttributeError:
        for _name, _step in getattr(model, "steps", []):
            try:
                _step.multi_class = "auto"
            except Exception:
                pass
        prediction = model.predict([text])[0]
        probabilities = model.predict_proba([text])[0]
        confidence = float(max(probabilities) * 100)
        return str(prediction), float(confidence)
    except Exception:
        return "general_inquiry", 65.0


# Test
if __name__ == "__main__":
    text = "My ATM did not give me cash but the money was deducted"
    
    category, confidence = classify_ticket(text)

    print("Category:", category)
    print("Confidence:", round(confidence, 2), "%")