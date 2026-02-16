"""StockStock 진입점.

사용법: python -m stockstock
"""

from stockstock.app import StockStockApp


def main() -> None:
    app = StockStockApp()
    app.run()


if __name__ == "__main__":
    main()
