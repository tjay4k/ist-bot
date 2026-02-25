import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class SheetsService:
    """
    Google Sheets API service.

    Provides authenticated access to Google Sehets for reading/writing data.
    """

    def __init__(self):
        """Initialize Google Sheets API client"""
        try:
            # Look for credentials.json in the project root
            creds_path = Path("config/sheets_credentials.json")

            if not creds_path.exists():
                logger.error(
                    f"credentials.json not found at: {creds_path.absolute()}")
                logger.error(
                    "Please place credentials.json in the project root directory")
                return

            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            logger.info("Loading Google Sheets credentials...")
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                str(creds_path),
                scope
            )

            logger.info("Authorizing with Google...")
            self.client = gspread.authorize(creds)
            logger.info("✓ Google Sheets client initialized successfully!")

        except FileNotFoundError:
            logger.error("credentials.json file not found!")
        except Exception as e:
            logger.error(
                f"Failed to initialize Sheets client: {e}", exc_info=True)

    def get_cell_value(self, spreadsheet, sheet_name: str, cell_address: str) -> str:
        """
        Get value from a specific cell, handling merged cells.

        Args:
            spreadsheet: gspread Spreadsheet object
            sheet_name: Name of the worksheet
            cell_address: Cell address (e.g., "E14" or "E14:F14" for merged)

        Returns:
            Cell value as string, or "N/A" if empty/error
        """
        try:
            sheet = spreadsheet.worksheet(sheet_name)

            # Handle merged cells (e.g., E14:F14)
            if ":" in cell_address:
                # For merged cells, get the first cell value
                start_cell = cell_address.split(":")[0]
                value = sheet.acell(start_cell).value
            else:
                value = sheet.acell(cell_address).value

            # Return "N/A" if empty
            return value.strip() if value and value.strip() else "*Vacant*"

        except Exception as e:
            logger.error(
                f"Error fetching {cell_address} from {sheet_name}: {e}")
            return "*Vacant*"

    def open_by_url(self, url: str):
        """
        Open a spreadsheet by URL.

        Args:
            url: Google Sheets URL

        Returns:
            gspread Spreadsheet object

        Raises:
            Exception if client not initialized or spreadsheet not found
        """
        if not self.client:
            raise Exception(
                "Sheets client not initialized. Check credentials.json")

        return self.client.open_by_url(url)


async def setup(bot):
    """Register the sheets service with the bot"""
    sheets_service = SheetsService()
    bot.register_service("sheets", sheets_service)
    logger.info("Sheets service registered")
