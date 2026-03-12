from app.config import get_project_paths


def test_project_paths_exist() -> None:
    paths = get_project_paths()

    assert paths["base_dir"].name == "mlb-betting-model"
    assert paths["data_dir"].name == "data"
    assert paths["db_dir"].name == "db"
