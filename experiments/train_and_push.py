import os
import shutil
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
from dotenv import load_dotenv
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split


load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
BEST_MODEL_DIR = ROOT_DIR / "best_model"
BEST_MODEL_PATH = BEST_MODEL_DIR / "best_model.joblib"

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://localhost:9091")

EXPERIMENT_NAME = "Iris Classification PushGateway"


def push_metrics_to_gateway(run_id: str, accuracy: float, loss: float) -> None:
    registry = CollectorRegistry()

    accuracy_gauge = Gauge(
        "mlflow_accuracy",
        "Accuracy of MLflow experiment run",
        ["run_id"],
        registry=registry,
    )

    loss_gauge = Gauge(
        "mlflow_loss",
        "Loss of MLflow experiment run",
        ["run_id"],
        registry=registry,
    )

    accuracy_gauge.labels(run_id=run_id).set(accuracy)
    loss_gauge.labels(run_id=run_id).set(loss)

    push_to_gateway(
        PUSHGATEWAY_URL,
        job="mlflow_experiment",
        registry=registry,
    )


def train_one_model(learning_rate: float, epochs: int):
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    X, y = load_iris(return_X_y=True)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    model = LogisticRegression(
        max_iter=epochs,
        C=1.0 / learning_rate,
        solver="lbfgs",
    )

    with mlflow.start_run() as run:
        run_id = run.info.run_id

        mlflow.log_param("learning_rate", learning_rate)
        mlflow.log_param("epochs", epochs)
        mlflow.log_param("model_type", "LogisticRegression")

        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)

        accuracy = accuracy_score(y_test, y_pred)
        loss = log_loss(y_test, y_proba)

        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("loss", loss)

        mlflow.sklearn.log_model(model, artifact_path="model")

        push_metrics_to_gateway(
            run_id=run_id,
            accuracy=accuracy,
            loss=loss,
        )

        print(
            f"Run ID: {run_id} | "
            f"learning_rate={learning_rate} | "
            f"epochs={epochs} | "
            f"accuracy={accuracy:.4f} | "
            f"loss={loss:.4f}"
        )

        return {
            "run_id": run_id,
            "learning_rate": learning_rate,
            "epochs": epochs,
            "accuracy": accuracy,
            "loss": loss,
            "model": model,
        }


def save_best_model(best_result: dict) -> None:
    if BEST_MODEL_DIR.exists():
        shutil.rmtree(BEST_MODEL_DIR)

    BEST_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(best_result["model"], BEST_MODEL_PATH)

    metadata_path = BEST_MODEL_DIR / "metadata.txt"
    metadata_path.write_text(
        "\n".join(
            [
                f"run_id={best_result['run_id']}",
                f"learning_rate={best_result['learning_rate']}",
                f"epochs={best_result['epochs']}",
                f"accuracy={best_result['accuracy']}",
                f"loss={best_result['loss']}",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Best model saved to: {BEST_MODEL_PATH}")


def main() -> None:
    parameter_grid = [
        {"learning_rate": 0.01, "epochs": 100},
        {"learning_rate": 0.05, "epochs": 150},
        {"learning_rate": 0.1, "epochs": 200},
        {"learning_rate": 0.2, "epochs": 300},
    ]

    results = []

    for params in parameter_grid:
        result = train_one_model(
            learning_rate=params["learning_rate"],
            epochs=params["epochs"],
        )
        results.append(result)

    best_result = max(results, key=lambda item: item["accuracy"])

    print("\nBest run:")
    print(f"Run ID: {best_result['run_id']}")
    print(f"Accuracy: {best_result['accuracy']:.4f}")
    print(f"Loss: {best_result['loss']:.4f}")

    save_best_model(best_result)


if __name__ == "__main__":
    main()
    