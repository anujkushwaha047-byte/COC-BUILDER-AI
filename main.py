from pathlib import Path
import tkinter as tk

from coc_observer.dashboard import Dashboard
from coc_observer.storage import ObservationStore


def main():
    root = tk.Tk()
    database_path = Path.home() / "AppData" / "Local" / "CoCObserver" / "observations.sqlite3"
    Dashboard(root, ObservationStore(database_path))
    root.mainloop()


if __name__ == "__main__":
    main()
