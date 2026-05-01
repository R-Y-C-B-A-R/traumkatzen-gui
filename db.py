import pymysql
import yaml
from pathlib import Path


def load_config():
    config_path = Path(__file__).parent / "config.yml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_connection():
    cfg = load_config()["database"]
    return pymysql.connect(
        host=cfg["host"],
        port=cfg.get("port", 3306),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_all_katzen(
    search: str = "",
    show_aktiv: bool = True,
    show_pausiert: bool = True,
    show_vermittelt: bool = True,
) -> list[dict]:
    status_filters = []
    if show_aktiv:
        status_filters.append("(vermittelt IS NULL AND pausiert IS NULL)")
    if show_pausiert:
        status_filters.append("pausiert IS NOT NULL")
    if show_vermittelt:
        status_filters.append("vermittelt IS NOT NULL")

    if not status_filters:
        return []

    status_sql = " OR ".join(status_filters)
    params = []
    where = f"({status_sql})"

    if search:
        where += " AND name LIKE %s"
        params.append(f"%{search}%")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, name, url, vermittelt, pausiert, krankheiten_handicaps "
                f"FROM katzen WHERE {where} ORDER BY name",
                params,
            )
            return cur.fetchall()


def fetch_katze(katze_id: int) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM katzen WHERE id = %s", (katze_id,))
            return cur.fetchone()


def save_katze(katze_id: int, data: dict) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE katzen SET
                    name = %s,
                    url = %s,
                    vermittelt = %s,
                    pausiert = %s,
                    krankheiten_handicaps = %s,
                    patenschaft_text = %s
                WHERE id = %s""",
                (
                    data["name"] or None,
                    data["url"] or None,
                    data["vermittelt"] or None,
                    data["pausiert"] or None,
                    data["krankheiten_handicaps"] or None,
                    data["patenschaft_text"] or None,
                    katze_id,
                ),
            )
        conn.commit()
