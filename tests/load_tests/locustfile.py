from locust import HttpUser, task, between
import random
import string


def random_string(length=8):
    """Генерация случайной строки."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


class LinkShortenerUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.test_short_code = None
        response = self.client.post(
            "/links/shorten", json={"original_url": "https://example.com"}
        )
        if response.status_code == 200:
            self.test_short_code = response.json()["short_url"].split("/")[-1]

    @task(3)
    def create_short_link(self):
        """Массовое создание коротких ссылок."""
        custom_alias = random_string()
        payload = {"original_url": "https://example.com", "custom_alias": custom_alias}
        response = self.client.post("/links/shorten", json=payload)

        if response.status_code == 200:
            response.success()
        else:
            response.failure(f"Ошибка создания ссылки: {response.status_code}")

    @task(2)
    def redirect_to_original_url(self):
        """Редирект по короткой ссылке."""
        if self.test_short_code:
            with self.client.get(
                f"/{self.test_short_code}", allow_redirects=False, catch_response=True
            ) as response:
                if response.status_code in (307, 302):
                    response.success()
                else:
                    response.failure(f"Ошибка редиректа: {response.status_code}")
