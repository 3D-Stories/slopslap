from slopslap_verification.editscript import Edit, map_region_status


def test_unchanged_when_no_edit_intersects():
    interval, status = map_region_status([Edit(20, 22, b"XX")], 0, 10)
    assert status == "unchanged" and interval == (0, 10)


def test_modified_when_edit_inside_region():
    # edit fully inside the region; boundaries map cleanly -> modified
    interval, status = map_region_status([Edit(4, 6, b"Z")], 0, 10)
    assert status == "modified"
    assert interval == (0, 9)  # region shrank by 1 (len 2 -> len 1)


def test_deleted_when_edit_fully_covers_region():
    interval, status = map_region_status([Edit(0, 12, b"")], 2, 8)
    assert status == "deleted"
    assert interval == (0, 0)  # tombstone at the mapped insertion point


def test_ambiguous_when_boundary_inside_edit():
    interval, status = map_region_status([Edit(4, 10, b"Z")], 6, 14)
    assert status == "ambiguous" and interval is None
