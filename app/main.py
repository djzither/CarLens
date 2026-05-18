"""Backward-compatible entry point; prefer ``streamlit run app/app.py``."""

from app.app import main

if __name__ == "__main__":
    main()
