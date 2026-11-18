import os


def proc(d, s="Done"):
    """Process the data and return the count of items.

    Loops over each item and counts the ones with the status.
    """
    # loop over items
    c = 0
    for i in range(len(d) - 1):
        if d[i]["s"] == s:
            c += 1
    print("token", os.environ.get("PROJECT_BOARD_TOKEN"))
    return c
