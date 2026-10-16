import pandas as pd
import joblib
from config import TEST_DATA_PATH, MODEL_PATH
from sklearn.metrics import accuracy_score, classification_report

# Load test dataset
test_data = pd.read_csv(TEST_DATA_PATH)

X_test = test_data["text"]
y_test = test_data["category"]

# Load trained model
model = joblib.load(MODEL_PATH)

# Predict
y_pred = model.predict(X_test)

# Accuracy
accuracy = accuracy_score(y_test, y_pred)

print("\nModel Evaluation")
print("----------------")
print("Test Accuracy:", round(accuracy * 100, 2), "%")

# Detailed report
print("\nClassification Report:")
print(classification_report(y_test, y_pred))