import joblib
from config import MODEL_PATH
m = joblib.load(MODEL_PATH)
print("Model type:", type(m))
print("Total classes:", len(m.classes_))
print("All classes:")
for i, c in enumerate(sorted(m.classes_)):
    print(f"  {i+1:3}. {c}")
