"""Run against a freshly seeded demo database. The flow changes the demo accounts."""

import os
import statistics
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("DORMBUDDY_BROWSER_URL", "http://127.0.0.1:8000")
PASSWORD = os.environ["DORMBUDDY_DEMO_PASSWORD"]
SCREENSHOTS = Path(os.environ.get("DORMBUDDY_SCREENSHOTS", "/tmp/dormbuddy-screenshots"))


def login(page, name):
    page.goto(BASE + "/login")
    page.get_by_label("Email").fill(f"{name}@example.com")
    page.get_by_label("Пароль").fill(PASSWORD)
    page.get_by_role("button", name="Войти").click()
    expect(page.get_by_role("heading", name="Соседи", exact=True)).to_be_visible()


def save_screens(page, width):
    page.goto(BASE + "/login")
    expect(page.get_by_role("img", name="DormBuddy")).to_be_visible()
    for screen, expected in [("login", "Войти"), ("neighbors", "Борис"), ("housing", "Жильё"), ("buddy", "AI Buddy")]:
        if screen == "neighbors":
            login(page, "alisa")
        elif screen != "login":
            page.goto(f"{BASE}/{screen}")
        expect(page.get_by_role("heading", name=expected, exact=True)).to_be_visible()
        page.evaluate("document.fonts.ready")
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth"), (width, screen)
        page.screenshot(path=SCREENSHOTS / f"{screen}-{width}.png", full_page=True)


def registration_and_housing(page):
    page.goto(BASE + "/register")
    page.get_by_label("Email").fill(f"new-{uuid4().hex}@example.com")
    page.get_by_label("Пароль").fill(PASSWORD)
    page.get_by_role("button", name="Зарегистрироваться").click()
    expect(page.get_by_role("heading", name="Профиль и анкета")).to_be_visible()
    page.goto(BASE + "/neighbors")
    expect(page.get_by_role("heading", name="Заполни условия подбора")).to_be_visible()
    page.get_by_role("link", name="Смотреть жильё").click()
    expect(page.get_by_role("heading", name="Жильё", exact=True)).to_be_visible()
    page.locator("#location").fill("сокол")
    page.locator("#minimum").fill("30000")
    page.locator("#maximum").fill("30000")
    page.locator("#kind").select_option("apartment")
    page.locator("#pets").select_option("yes")
    page.locator("#smoking").select_option("no")
    page.get_by_role("button", name="Применить").press("Enter")
    expect(page.locator(".listing-card")).to_have_count(1)
    page.get_by_role("link", name="Подробнее").click()
    expect(page.get_by_role("heading", name="Двухкомнатная у Сокола")).to_be_visible()
    page.get_by_role("button", name="В избранное").click()
    page.goto(BASE + "/housing/favorites")
    expect(page.get_by_role("heading", name="Двухкомнатная у Сокола")).to_be_visible()
    page.get_by_role("button", name="Убрать из избранного").click()
    expect(page.get_by_role("heading", name="В избранном пока пусто")).to_be_visible()

    page.goto(BASE + "/profile")
    page.locator("#display_name").fill("Участник браузерной проверки")
    page.locator("#budget_min").fill("35000")
    page.locator("#budget_max").fill("30000")
    page.get_by_role("button", name="Сохранить анкету").click()
    expect(page.get_by_role("alert")).to_contain_text("Проверь отмеченные поля.")
    expect(page.locator("#budget_max")).to_have_attribute("aria-invalid", "true")


def match_flow(alice, boris):
    login(alice, "alisa")
    login(boris, "boris")
    expect(alice.get_by_role("heading", name="Борис")).to_be_visible()
    expect(alice.get_by_text("Сопоставлено 6 из 6 предпочтений.")).to_be_visible()
    expect(boris.get_by_role("heading", name="Алиса")).to_be_visible()
    timings = []
    for _ in range(30):
        start = perf_counter()
        assert alice.request.get(BASE + "/neighbors").ok
        timings.append((perf_counter() - start) * 1000)
    print(f"/neighbors 30×, median {statistics.median(timings):.1f} ms, "
          f"p95 {statistics.quantiles(timings, n=20, method='inclusive')[18]:.1f} ms, max {max(timings):.1f} ms")

    skip = alice.get_by_role("button", name="Пропустить")
    skip.focus()
    alice.keyboard.press("Tab")
    like = alice.get_by_role("button", name="Нравится")
    expect(like).to_be_focused()
    assert like.evaluate("(button) => button.matches(':focus-visible')")
    alice.keyboard.press("Enter")
    expect(alice.get_by_role("heading", name="Мила")).to_be_visible()
    expect(alice.get_by_text("Недостаточно данных", exact=True)).to_be_visible()
    alice.get_by_role("button", name="Пропустить").press("Enter")
    expect(alice.get_by_role("heading", name="Подходящих анкет пока нет")).to_be_visible()
    alice.goto(BASE + "/matches")
    expect(alice.get_by_role("heading", name="Пока нет взаимных симпатий")).to_be_visible()
    boris.get_by_role("button", name="Нравится").press("Enter")
    expect(boris.get_by_role("status")).to_contain_text("взаимная симпатия")
    for page in (alice, boris):
        page.goto(BASE + "/matches")
        page.get_by_role("link", name="Общее жильё").click()
        expect(page.locator(".listing-card")).to_have_count(1)
        expect(page.get_by_role("heading", name="Двухкомнатная у Сокола")).to_be_visible()


def dorm_flow(page):
    login(page, "nadya")
    expect(page.get_by_role("heading", name="Олег")).to_be_visible()
    expect(page.get_by_text("Расселением занимается вуз.", exact=False)).to_be_visible()
    page.get_by_role("link", name="Общежитие", exact=True).click()
    expect(page.locator("#budget_min")).to_be_hidden()
    expect(page.locator("#dormitory_id")).to_be_visible()
    page.locator("#dormitory_id").select_option(label="Общежитие № 2")
    page.get_by_role("button", name="Сохранить анкету").click()
    page.get_by_role("link", name="Посмотреть рекомендации").click()
    expect(page.get_by_role("heading", name="Соня")).to_be_visible()


def buddy_without_provider(page):
    page.goto(BASE + "/buddy")
    prompt = "Что купить для первых дней в общежитии?"
    page.get_by_role("button", name=prompt).click()
    expect(page.locator("#question")).to_have_value(prompt)
    page.get_by_role("button", name="Отправить").click()
    expect(page.get_by_role("alert")).to_contain_text("Вопрос сохранён.")
    page.get_by_role("button", name="Повторить вопрос").click()
    expect(page.locator(".user-bubble")).to_have_count(1)
    expect(page.locator(".user-bubble")).to_contain_text(prompt)
    page.get_by_role("navigation").get_by_role("link", name="Жильё").click()
    expect(page.get_by_role("heading", name="Жильё", exact=True)).to_be_visible()


if __name__ == "__main__":
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get("DORMBUDDY_CHROMIUM"))
        for width, height in [(390, 844), (1440, 900)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            save_screens(page, width)
            page.close()

        registration_and_housing(browser.new_page(viewport={"width": 390, "height": 844}))
        alice, boris = browser.new_page(), browser.new_page()
        match_flow(alice, boris)
        dorm_flow(browser.new_page())
        buddy_without_provider(alice)
        print("Chromium: 8 responsive screenshots; registration, housing, keyboard swipes, match, dorm, Buddy failure.")
