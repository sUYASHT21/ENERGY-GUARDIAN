from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_serves_spa_assets_and_fallback_without_shadowing_api(tmp_path, clock):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>dashboard</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("nope")
    app = create_app(make_settings(tmp_path, serve_frontend=True, frontend_dist=dist), clock)
    with TestClient(app) as c:
        assert c.get("/").text == "<html>dashboard</html>"
        assert c.get("/rooms/3").text == "<html>dashboard</html>"  # client-side route
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert "nope" not in c.get("/../secret.txt").text  # no path traversal
        assert c.get("/api/v1/health").json()["status"] == "ok"
        r = c.get("/api/v1/does-not-exist")
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_disabled_when_no_build_present(tmp_path, clock):
    app = create_app(make_settings(tmp_path, serve_frontend=True, frontend_dist=tmp_path / "missing"), clock)
    with TestClient(app) as c:
        assert c.get("/").status_code == 404
