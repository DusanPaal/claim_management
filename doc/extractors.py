# pylint: disable = C0301, W1203

"""Base module for data parsers."""

import math
import re
import os
import sys
from os.path import join
from abc import abstractmethod
from collections import OrderedDict
from datetime import date, datetime
from os.path import basename, splitext
from typing import Union
import yaml

from . import logger

g_log = logger.get_logger("global")

class PatternMatchError(Exception):
    """Unmatched or mismatched regex pattern(s) for a mandatory field."""

class PrimitiveParser:
    """Parses primitive data types."""

    def parse_number(
            self, val: str,
            coerce: str = None,
            strip_vals: list = None,
            errors: str = "raise"
        ) -> Union[float,int]:
        """
        Converts a string amount into a float.

        Params:
        -------
        val:
            A string representing the amount value to convert. \n
            If the string contains any witespaces, these will be \n
            stripped before parsing.

        coerce:
            Indicates whether the pared number should be converted \n
            into a specific data type. Available values:
            - None (default): data type of the resulting number will be inferred
            - 'int': resulting number will be converted to an integer
            - 'float': resulting number will be converted to a float

        errors:
            Action to take if an error is encountered:
            - 'raise': Exceptions will be raised.
            - 'ignore': Exceptions won't be raised and the original input value will be returned.

        Returns:
        --------
        Parsed number.

        Examples:
        --------
        >>> parse_number('125,30-')
        >>> -125.3

        >>> parse_number('1.254.125,33-')
        >>> -1254125.33

        >>> parse_number('1.254.125.33-')
        >>> -1254125.33

        >>> parse_number('1,254,125,33-')
        >>> -1254125.33

        >>> parse_number('125.33')
        >>> 125.33

        >>> parse_number('125,5400')
        >>> 125.54

        >>> parse_number('1,000', coerce = 'int')
        >>> 1

        Raises:
        -------
        Values with type other than `str` raise a TypeError.
        Values with type `str` that don't represent a number raise a ValueError.
        """

        if errors not in ["raise", "ignore"]:
            raise ValueError(f"Unrecognized value '{errors}' used!")

        if not isinstance(val, str):
            if errors == "raise":
                raise TypeError(f"Expected value type was 'str', but got '{val}'!")
            if errors == "ignore":
                return val

        for stripv in strip_vals or []:
            val = val.strip(stripv)

        repl = val.replace(" ", "")
        repl = repl.strip("-")
        decimals = 0

        # some documents contain amouts rounded
        # to 4 decimal places instead of 2
        if re.search(r"\D", repl) is not None:
            decimals = len(re.split(r"\D", repl)[-1])

        # some documents contian amouts rounded
        # to 4 decimal places instead of 2
        repl = repl.replace(".", "")
        repl = repl.replace(",", "")

        if not repl.isnumeric():
            if errors == "raise":
                raise TypeError("Only numeric values are accepted!")
            if errors == "ignore":
                return val

        parsed = int(repl)

        if decimals != 0:
            parsed /= 10**decimals

        if "-" in val:
            parsed *= -1

        if coerce == "int":
            parsed = int(parsed)
        elif coerce == "float":
            parsed = float(parsed)

        return parsed

    def parse_date(
            self, val: str, fmt: str, dst_fmt: str = None,
            target_type: str = "datetime") -> Union[date, datetime]:
        """
        Parses date and returns date after parsing.

        Params:
        -------
        val:
            String date to parse.

        fmt:
            String that defines the format of the input date.

        dst_fmt:
            String that controls the resulting date format. \n
            If `None` is used (default), then no final formatting \n
            will be applied and the result defined by 'target_type' \n
            parameter will be returned.

        target_type:
            Resulting data type.
            If invalid value is passed, then 'datetime' will be used.

        Returns:
        --------
        Parsed date as a datetime object.
        """

        if not isinstance(val, str):
            raise TypeError(f"Expected value type was 'str', but got '{val}'!")

        parsed = datetime.strptime(val, fmt)

        if target_type == "date":
            res = parsed.date()
        elif target_type == "datetime":
            res = parsed
        else:
            raise ValueError(f"Invalid target type: '{target_type}'!")

        if dst_fmt is not None:
            res = parsed.strftime(dst_fmt)

        return res

class CompositeParser(PrimitiveParser):
    """Parses composite data types."""

    _dispatcher = {}
    _template_id = None

    def _set_template_id(self, template_id: str):

        if template_id not in self._dispatcher:
            raise NotImplementedError(
                "No composite data parsing method implemented "
                f"for template with ID: '{template_id}'!"
            )

        self._template_id = template_id

    @abstractmethod
    def parse_items(self, items: list, amount: float) -> Union[list,None]:
        """
        Parses document items.

        Params:
        -------
        items: List of document items to parse.
        amount: Total document amount.

        Returns:
        --------
        List of parsed items.

        If parsing fails, then `None` is returned.

        Note:
        -----
        The total amount should always be checked against the sum of the partial
        amounts in the items listed on the document. So far, this is only done for
        OBI DE/AT, where the items are used in the process of automatically creating
        credit notes for the disputes. If the equality test is passed, the item is
        added to the database with the result. If not, the items are removed from
        the extraction result completely. However, if the items are missing, the
        'conventional penalty' automation will not be able to create a corresponding
        credit note if the CS decides to accept the customer's claim.
        """

class MarkantParser(CompositeParser):
    """Parser for Obi documents."""

    def __init__(self, template_id: str) -> None:
        """Constructor for class: `ObiParser`."""

        self._dispatcher = {
            "141001DE002": self._parse_bgl_debit,
            "141001DE011": self._parse_debit,
        }

        self._set_template_id(template_id)

    def parse_items(self, items: list, amount: float) -> list:
        """Parses document items."""

        return self._dispatcher[self._template_id](items, amount)

    def _parse_bgl_debit(self, items: list, amount: float) -> list:
        """Parses penalty type items."""

        doc_items_amount = 0
        calc_items_amount = 0
        result = []

        for item in items:

            doc_diff = self.parse_number(item[0], coerce = "float")
            pcs_ordered = self.parse_number(item[1], coerce = "int")
            pcs_delivered = self.parse_number(item[2], coerce = "int")
            price_ordered = self.parse_number(item[3], coerce = "float")
            price_delivered = self.parse_number(item[4], coerce = "float")

            result.append([doc_diff, pcs_ordered, pcs_delivered, price_ordered, price_delivered])

            if pcs_ordered == pcs_delivered:
                calc_diff = (price_delivered - price_ordered) * pcs_ordered
            else:
                calc_diff = (pcs_ordered - pcs_delivered) * price_delivered

            calc_items_amount += calc_diff
            doc_items_amount += doc_diff

        doc_items_amount = round(doc_items_amount, 2)
        calc_items_amount = round(calc_items_amount, 2)

        if doc_items_amount + calc_items_amount != amount * 2:
            raise RuntimeError("Sum of item amounts not equal to the document total amount!")
            self.logger.error("Sum of item amounts not equal to the document total amount!")
            g_log.warning("Field 'items' will be removed from extracted data.")
            return None

        return result

    def _parse_debit(self, items: list, amount: float) -> list:
        """Parses penalty type items."""

        doc_items_amount = 0
        calc_items_amount = 0
        result = []

        for item in items:

            doc_diff = self.parse_number(item[0], coerce = "float")
            pcs_ordered = self.parse_number(item[1], coerce = "int")
            pcs_delivered = self.parse_number(item[2], coerce = "int")
            price_ordered = self.parse_number(item[3], coerce = "float")
            price_delivered = self.parse_number(item[4], coerce = "float")

            result.append([doc_diff, pcs_ordered, pcs_delivered, price_ordered, price_delivered])

            if pcs_ordered == pcs_delivered:
                calc_diff = (price_delivered - price_ordered) * pcs_ordered
            else:
                calc_diff = (pcs_ordered - pcs_delivered) * price_delivered

            calc_items_amount += calc_diff
            doc_items_amount += doc_diff

        doc_items_amount = round(doc_items_amount, 2)
        calc_items_amount = round(calc_items_amount, 2)

        if doc_items_amount + calc_items_amount != amount * 2:
            g_log.error("Sum of item amounts not equal to the document total amount!")
            self.logger.error("Sum of item amounts not equal to the document total amount!")
            g_log.warning("Field 'items' will be removed from extracted data.")
            return None

        return result

class ObiParser(CompositeParser):
    """Parser for Obi documents."""

    def __init__(self, template_id: str) -> None:
        """Constructor for class: `ObiParser`."""

        self._dispatcher = {
            "161001DE005": self._parse_delivery,
            "161001DE001": self._parse_penalty,
            "161072AT005": self._parse_penalty,
            "161001DE007": self._parse_return,
        }

        self._set_template_id(template_id)

    def parse_items(self, items: list, amount: float) -> list:
        """Parses document items."""

        return self._dispatcher[self._template_id](items, amount)

    def _parse_delivery(self, items: list, amount: float) -> list:
        """Parses delivery type items."""

        result = []
        items_amount = 0

        for item in items:

            parsed_item = []

            for val in item:

                if re.fullmatch(r"\d+,\d{3}", val):
                    parsed_val = self.parse_number(val, coerce = "int")
                elif re.match(r"\d+,\d{4}", val):
                    parsed_val = self.parse_number(val, coerce = "float")
                elif re.match(r"\d+,\d{2}", val):
                    parsed_val = self.parse_number(val, coerce = "float")
                else:
                    parsed_val = val

                parsed_item.append(parsed_val)

            result.append(parsed_item)
            diff = parsed_item[5] - parsed_item[2]
            items_amount += diff

        # validate parsed data
        if round(items_amount, 2) != amount:
            g_log.error("Sum of item amounts not equal to the document total amount!")
            self.logger.error("Sum of item amounts not equal to the document total amount!")
            g_log.warning("Field 'items' will be removed from extracted data.")
            return None

        return result

    def _parse_return(self, items: list, amount: float) -> list:
        """Parses delivery type items."""

        result = []
        items_amount = 0

        for item in items:

            parsed_item = []

            for val in item:

                if val == "":  # Rabatt
                    parsed_val = 0.0
                elif val.isnumeric(): # LAR
                    parsed_val = self.parse_number(val, coerce = "int")
                elif re.fullmatch(r"\d+,\d{3}", val): # Menge
                    parsed_val = self.parse_number(val, coerce = "int")
                elif re.match(r"\d+,\d{4}", val): # EK-Preis
                    parsed_val = self.parse_number(val, coerce = "float")
                elif re.match(r"\d+,\d{2}", val): # PosWert
                    parsed_val = self.parse_number(val, coerce = "float")
                else:
                    parsed_val = val

                parsed_item.append(parsed_val)

            result.append(parsed_item)
            items_amount += parsed_item[-1]

        # validate parsed data
        if round(items_amount, 2) != amount:
            g_log.error("Sum of item amounts not equal to the document total amount!")
            self.logger.error("Sum of item amounts not equal to the document total amount!")
            g_log.warning("Field 'items' will be removed from extracted data.")
            return None

        return result

    def _parse_penalty(self, items: list, amount: float) -> list:
        """Parses penalty type items."""

        items_amount = 0
        err_tax_rate =  False
        result = []

        for item in items:

            partial_penalty = self.parse_number(item[0])
            po_number = self.parse_number(item[1], coerce = "int")
            item_amount = self.parse_number(item[2])
            parsed = [partial_penalty, po_number, item_amount]
            result.append(parsed)

            calc_rate = int(partial_penalty / item_amount * 100)

            if calc_rate in (2, 25):
                items_amount += partial_penalty
                continue

            # possible reason: incorrect data extraction or mistake made by the customer
            self.logger.error("Invalid tax rate %.2f %% in document items!", calc_rate)
            g_log.error("Invalid tax rate %.2f %% in document items!", calc_rate)
            g_log.warning("Field 'items' will be removed from extracted data.")
            err_tax_rate = True
            break

        if err_tax_rate:
            return None

        if round(items_amount, 2) != amount:
            g_log.error("Sum of item amounts not equal to the document total amount!")
            self.logger.error("Sum of item amounts not equal to the document total amount!")
            g_log.warning("Field 'items' will be removed from extracted data.")
            return None

        return result

class RollerParser(CompositeParser):
    """Parser for Roller documents."""

    def __init__(self, template_id: str) -> None:
        """Constructor for class: `RollerParser`."""

        self._dispatcher = {
            "171001DE001": self._parse_return,
        }

        self._set_template_id(template_id)

    def parse_items(self, items: list, amount: float) -> list:
        """Parses document items."""

        return self._dispatcher[self._template_id](items, amount)

    def _parse_return(self, items: list, amount: float) -> list:
        """Parses deli  very type items."""

        result = []
        items_amount = 0

        for item in items:

            n_pieces = self.parse_number(item[0], coerce = "int")
            amount_net = self.parse_number(item[1], coerce = "float")
            tax_rate = self.parse_number(item[2], coerce = "float")
            amount_tax = self.parse_number(item[3], coerce = "float")
            amount_gross = self.parse_number(item[4], coerce = "float")

            if n_pieces <= 0:
                raise ValueError("Number of pieces must be a positive integer!")

            if tax_rate not in (19.0, 0.0):
                raise ValueError(f"Incorrect tax rate: {tax_rate}!")

            if amount_gross <= 0:
                raise ValueError("Item gross amount must be a positive float!")

            result.append([n_pieces, amount_net, tax_rate, amount_gross])

            items_amount = amount_net + amount_tax

        # validate parsed data
        if round(items_amount, 2) != amount:
            g_log.error("Sum of item amounts not equal to the document total amount!")
            self.logger.error("Sum of item amounts not equal to the document total amount!")
            g_log.warning("Field 'items' will be removed from extracted data.")
            return None

        return result

class ToomParser(CompositeParser):
    """Parser for Toom documents."""

    def __init__(self, template_id: str):
        """Constructor for class: `RollerParser`."""

        self._dispatcher = {
            "181001DE001": self._parse_return,
        }

        self._set_template_id(template_id)

    def parse_items(self, items: list, amount: float) -> list:
        """Parses document items."""

        return self._dispatcher[self._template_id](items, amount)

    def _parse_return(self, items: list, amount: float) -> list:
        """Parses return type items."""

        result = []
        items_gross_amount = 0

        for item in items:
            tax_rate = self.parse_number(item[0], coerce = "float")
            n_pieces = self.parse_number(item[1], coerce = "int")
            amount_net = self.parse_number(item[2], coerce = "float")
            result.append([tax_rate, n_pieces, amount_net])
            items_gross_amount += amount_net * n_pieces * (1 + tax_rate / 100)

        # validate parsed data
        if not math.isclose(items_gross_amount, amount, rel_tol = 0.01):
            g_log.error("Sum of item amounts not equal to the document total amount!")
            self.logger.error("Sum of item amounts not equal to the document total amount!")
            g_log.warning("Field 'items' will be removed from extracted data.")
            return None

        return result

# data extraction class
class Template(OrderedDict):
    """
    Represents a template that lives
    as a single .yml file on the disk.
    """

    _unique_value_fields = [
        "amount",
        "document_number",
        "archive_number",
        "return_number",
        "agreement_number",
        "supplier",
        "subtotals",
        "identifier",
        "branch",
        "zip",
    ]

    _categs = [
        "bonus",
        "delivery",
        "finance",
        "invoice",
        "penalty_general",
        "penalty_delay",
        "penalty_quote",
        "price",
        "promo",
        "quality",
        "rebuild",
        "return"
    ]


    def __init__(self, *args, **kwargs) -> None:
        """
        Constructor of class: `Template`.

        See docuemntation for OrderedDict for a detailed
        description of `args` and `kwargs` arguments.
        """

        super(Template, self).__init__(*args, **kwargs)

        # set default options
        self._options = {
            "remove_whitespace": False,
            "lowercase": False,
            "replace": [],
            "date_formats": []
        }

        # Merge template-specific options with defaults
        self._options.update(self.get("options", {}))

        # check the integrity of header fields
        for fld in ["issuer", "kind", "name", "template_id"]:
            if fld not in self.keys() or self[fld] is None:
                raise KeyError(
                    f"Could not load template '{self['name']}'! "
                    f"Field '{fld}' missing from the template header."
                )

        # NOTE: Categorization is valid only for debits and makes no sense
        # for credit notes the current clam handling process.

        # Ensure, that field 'category' has correct data type and format
        # For credit notes, set the 'category' field to `None` value.
        if self["kind"] == "credit":
            self["category"] = None
        elif self["kind"] == "debit":
            if "category" not in self.keys():
                raise KeyError(
                    f"Could not load the template '{self['name']}'! "
                    "Field 'category' missing from the template header."
                )

            if isinstance(self["category"], str):
                used_categs = [self["category"]]
            elif isinstance(self["category"], list):
                used_categs = self["category"]
            else:
                raise TypeError(
                    "Expected was 'category' value with type 'str' "
                    f"or 'list[str]', but got '{type(used_categs)}'!"
                )

            unrecognized_categs = set(used_categs).difference(self._categs)

            if len(unrecognized_categs) != 0:
                raise ValueError(
                    f"Could not load the template '{self['name']}'! "
                    f"Unrecognized 'category' value(s): {unrecognized_categs}."
                )

        if self["category"] is not None:
            if isinstance(self["category"], list):
                self["category"] = [categ.lower() for categ  in self["category"]]
            elif isinstance(self["category"], str):
                self["category"] = self["category"].lower()
            else:
                raise TypeError(f"Unsupported data type for 'category' field: {type(self['category'])}!")

        # ensure proper casing of header field values
        self["issuer"] = self["issuer"].upper()
        self["kind"] = self["kind"].lower()
        self["template_id"] = self["template_id"].upper()

        if self["kind"] == "debit":
            if isinstance(self["category"], str):
                self["category"] = self["category"].lower()
            elif isinstance(self["category"], list):
                self["category"] = [val.lower() for val in self["category"]]
            else:
                raise TypeError(f"Unsupported type: '{type(self['category'])}' for 'category' field!")

    def _validate_numbering(self, val: Union[str,list], field: str = None):
        """Validates the correctness of delivery note number(s)."""

        if isinstance(val, list):
            nums = val
        elif isinstance(val, str):
            nums = [val]
        else:
            raise TypeError(f"Value with type 'str' or 'list' expected, but got '{type(val)}'!")

        for num in nums:
            if field is None:
                if not num.isnumeric():
                    raise ValueError(f"Invalid number: {num}!")
            elif field == "delivery_number":
                if not num.startswith("31") or len(num) != 9:
                    raise ValueError(f"Invalid delivery note number: {num}!")
            elif field == "invoice_number":
                if not num.isnumeric() or num.startswith("0") or len(num) != 9:
                    raise ValueError(f"Invalid invoice number: {num}!")
            elif field == "purchase_order_number":
                if not num.isnumeric() or num.startswith("0") or not 5 <= len(num) <= 7:
                    raise ValueError(f"Invalid purchase order number: {num}!")
            elif field == "return_number":
                if not (num.isnumeric() and len(num) in (6,7)):
                    raise ValueError(f"Invalid return number: {num}!")
            elif field == "agreement_number":
                if not (num.isnumeric() or len(num) == 10):
                    raise ValueError(f"Invalid agreement number: {num}!")
            else:
                raise ValueError(f"Unrecognized numbering type: '{field}'!")

    def _match_patterns(
            self, text: str, regex: Union[str,list],
            duplicates: bool = False) -> list:
        """Performs matching of multiple regex patters on a text."""

        # ensure patts are placed in a list container
        rx_patts = regex if isinstance(regex, list) else [regex]
        res_find = []

        for patt in rx_patts:

            matches = re.findall(patt, text)

            if len(matches) == 0:
                continue

            res_find.extend(matches)

            break

        if not duplicates:
            res_find = list(set(res_find))

        return res_find

    def prepare_input(self, raw_str: str) -> str:
        """
        Transform raw string using settings
        from 'options' section of the template file.

        Params:
        -------
        raw_str: String to transform.

        Returns:
        --------
        Transformed string.
        """

        # Remove excessive withspace
        if self._options["remove_whitespace"]:
            optimized_str = re.sub(r"\s{2,}", "", raw_str)
        else:
            optimized_str = raw_str

        # convert to lower case
        if self._options["lowercase"]:
            optimized_str = optimized_str.lower()

        # specific replace
        for repl in self._options["replace"]:
            if len(repl) != 2:
                raise ValueError("A replace should be a list of 2 items!")
            optimized_str = re.sub(repl[0], repl[1], optimized_str)

        return optimized_str

    def matches_keywords(self, text: str) -> bool:
        """Check if document text matches all keywords stated in the template file."""

        inclusive = [bool(re.findall(kwd, text)) for kwd in self["inclusive_keywords"]]

        # these types ow keywords are optional when excluding
        # certain substrings is needed to filter on document types
        if "exclusive_keywords" in self:
            exclusive = [bool(re.findall(kwd, text)) for kwd in self["exclusive_keywords"]]
        else:
            exclusive = []

        if all(inclusive) and not any(exclusive):
            self.logger.info("Matched template: '%s'", self["name"])
            return True

        return False

    def extract(self, text: str, psr: CompositeParser) -> dict:
        """Given a template file and a string, extract matching data fields."""

        self.logger.info("Date parsing: date_formats = %s", self._options["date_formats"])
        self.logger.info("Inclusive keywords = %s", self["inclusive_keywords"])
        self.logger.info("Exclusive keywords = %s", self.get("exclusive_keywords", []))
        self.logger.info("Options = %s", self._options)

        output = OrderedDict()
        output["issuer"] = self["issuer"]
        output["name"] = self["name"]
        output["kind"] = self["kind"]
        output["template_id"] = self["template_id"]
        output["category"] = self["category"]

        optional_fields = self.get("optional_fields", [])

        # Try to find data for each field.
        for fld, regex in self["fields"].items():

            allow_duplicates = fld == "items"
            result = self._match_patterns(text, regex, allow_duplicates)

            if len(result) == 0:
                # do not raise exception even if no value was found,
                # but keep matching to get as much data as possible
                if fld in optional_fields:
                    self.logger.warning(f"regexp '{regex}' for optional field '{fld}' didn't match!")
                else:
                    self.logger.error(f"regexp '{regex}' for field '{fld}' didn't match!")
            elif len(result) > 1 and fld in self._unique_value_fields:
                self.logger.error(f"Field '{fld}': regex pattern '{regex}' should match a unique value, but found: {result}!")
                raise PatternMatchError(f"Field '{fld}': regex pattern '{regex}' matched multiple values while only one is expected!")
            elif fld == "amount":
                output[fld] = self.parser.parse_number(result[0], coerce = "float")
                if output[fld] <= 0.0:
                    raise ValueError("Extracted document amount must be a non-zero positive float!")
            elif fld in ("zip", "archive_number", "branch"):
                self._validate_numbering(result[0])
                output[fld] = self.parser.parse_number(result[0], coerce = "int")
            elif fld in ("supplier", "document_number", "identifier"):
                output[fld] = self.parser.parse_number(result[0], coerce = "int", errors = "ignore")
            elif fld == "tax":
                if len(result) == 1:
                    output[fld] = self.parser.parse_number(result[0], coerce = "float", strip_vals = ["%"])
                else:
                    output[fld] = self.parser.parse_numbers(result, coerce = "float", strip_vals = ["%"])
            elif fld == "subtotals":
                output[fld] = self.parser.parse_numbers(result[0], coerce = "float")
            elif fld in ("delivery_number", "invoice_number", "purchase_order_number", "return_number", "agreement_number"):
                self._validate_numbering(result, fld)
                if len(result) == 1:
                    output[fld] = self.parser.parse_number(result[0], coerce = "int")
                else:
                    output[fld] = self.parser.parse_numbers(result, coerce = "int")
            elif fld == "items":
                # NOTE: in yaml templates, items must always come after amount, otherwise item parsing won't be possibe - consider refactoring
                output[fld] = psr.parse_items(result, output["amount"])
            else:
                output[fld] = result[0]

            self.logger.info(f"field: '{fld}' | result: {result} | regexp: '{regex}'")

        # If required fields were found, return output, else log error.
        templ_fields = set(self["fields"]) # list of all field names in a tempate
        req_fields = templ_fields.difference(optional_fields)
        req_unmatched = set(req_fields).difference(output.keys())
        req_unmatched = list(req_unmatched)

        if len(req_unmatched) != 0:
            self.logger.error(f"Required fields unmatched: {req_unmatched}")
            raise PatternMatchError(f"Required fields unmatched: {req_unmatched}")

        # each data dict must contain at least
        # these filelds once parsing is done
        assert output["issuer"] is not None
        assert output["name"] is not None
        assert output["kind"] is not None
        assert output["document_number"] is not None
        assert output["amount"] is not None
        assert output["template_id"] is not None

        return dict(output)

    @property
    def logger(self):
        """Docuemnt logger."""
        return self._doclog

    @logger.setter
    def logger(self, lgr: ExtLogger):
        """Docuemnt logger."""
        self._doclog = lgr

class Extractor:
    """
    The class manages matching the document
    text with data extraction templates and
    data extraction from the document text.
    """

    _templates = []

    _parsers = {
        "OBI": ObiParser,
        "MARKANT": MarkantParser,
        "ROLLER": RollerParser,
        "TOOM": ToomParser
    }

    def __init__(self, issuer: str):
        """
        Creates a document data extractor for a specific customer.

        Params:
        -------
        issuer: Customer name and country (e.g. "OBI_DE")
        """

        templates_dir = join(sys.path[0], "engine", "templates", issuer)

        for tpl_path in os.listdir(templates_dir):
            tpl = self._load_template(tpl_path)
            self._templates.append(tpl)

    def _load_template(self, tpl_path: str):

        with open(tpl_path, encoding = "utf-8") as stream:
            content = yaml.safe_load(stream)

        tpl = Template(content)
        tpl["name"] = splitext(basename(tpl_path))[0]

        if "optional_fields" in tpl["fields"].keys():
            raise KeyError("Field 'optional_fields' misplaced!")

        # Test if all required fields are in the correct place template:
        if "inclusive_keywords" not in tpl.keys():
            raise KeyError(f"Field 'inclusive_keywords' missing from template '{tpl['name']}'!")

        # Keywords as list, if only one.
        if not isinstance(tpl["inclusive_keywords"], list):
            tpl["inclusive_keywords"] = [tpl["inclusive_keywords"]]

        self._templates.append(Template(tpl))

    def match_text(self, text: str) -> Union[str,None]:
        """
        Checks if a text matches one
        of the extractor's data templates.

        Params:
        -------
        text: Text extracted from the document.

        Returns:
        --------
        If the text matches one of the extraction templates \n
        the string ID of the matched template is returned, \n
        otherwise `None`.
        """

        for tpl in self._templates:
            if tpl.matches_keywords(text):
                return tpl["template_id"]

        return None

    def extract(self, text: str, templ_id: str, log_path: str) -> dict:
        """
        Extracts relevant data from document text.

        Params:
        -------
        templ_id: The string ID of the matched template.

        Returns:
        --------
        Extracted data that consists of fields and the respective parameters.
        """

        tmpl: Template = self._templates[templ_id]
        customer = tmpl["issuer"].split("_")[0]
        parser = self._parsers[customer](templ_id)
        tmpl.logger = ExtLogger("document", log_path)
        result = tmpl.extract(text, parser)

        return result
