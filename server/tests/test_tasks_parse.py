from ide_server.tasks.parse import parse_meta


def test_title_from_h1():
    assert parse_meta("# Mi tarea\ntexto")["title"] == "Mi tarea"


def test_h2_no_es_titulo():
    assert parse_meta("## Sub\ntexto")["title"] is None


def test_status_line():
    assert parse_meta("# T\nstatus: doing\n")["status"] == "doing"


def test_status_case_insensitive():
    assert parse_meta("Status:  Done  ")["status"] == "Done"


def test_sin_meta():
    m = parse_meta("solo texto\nmás texto")
    assert m == {"title": None, "status": None}


def test_primer_h1_gana():
    assert parse_meta("# Uno\n# Dos")["title"] == "Uno"
