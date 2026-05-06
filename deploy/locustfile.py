"""Locust load test for nami-core API."""

from locust import HttpUser, task, between


class NamiCoreUser(HttpUser):
    """Simulated user hitting nami-core endpoints."""

    wait_time = between(0.5, 2)
    host = "http://127.0.0.1:8092"

    @task(5)
    def health(self):
        self.client.get("/health")

    @task(3)
    def workers(self):
        self.client.get("/workers")

    @task(2)
    def metrics(self):
        self.client.get("/metrics")

    @task(1)
    def dispatch(self):
        self.client.post("/dispatch", json={
            "worker": "default",
            "action": "echo",
            "payload": {"message": "load test"},
        }, headers={"Authorization": "Bearer load-test-key"})

    @task(1)
    def scheduler(self):
        self.client.get("/scheduler")
