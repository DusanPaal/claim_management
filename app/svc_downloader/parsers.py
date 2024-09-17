
"""Parsing of strings."""

import re
from datetime import date, datetime
from typing import Union

class PatternMatchError(Exception):
    """Unmatched or mismatched regex pattern(s) for a mandatory field."""

class TemplateNotFoundError(Exception):
    """Attempt to match data with any template fails."""

class ParsingError(Exception):
    """Parsing of teh string value fails."""

class PrimitiveParser:
    """Parse strings to primitive data types."""

    def parse_number(
            self, val: str, coerce: str = None,
            errors: str = "raise") -> Union[float,int]:
        """
        Parse a numeric string.

        Params:
        -------
        val:
            Value to parse.
            Any witespaces are removed before parsing.

        coerce:
            Indicates whether the pared number should be converted \n
            into a specific data type. Available values:
            - `None` (default): data type of the resulting number will be inferred
            - `int`: resulting number will be converted to an integer
            - `float`: resulting number will be converted to a float

        errors:
            Action to take if an error is encountered durig parsing:
            - "raise": Exceptions will be raised.
            - "ignore": Exceptions won't be raised and the original input value will be returned.

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
        ValueError:
            If an invalid parameter value is passed or
            the value to be parsed is a `str` but doesn't
            represent a number.
        """

        if errors not in ["raise", "ignore"]:
            raise ValueError(f"Unrecognized value '{errors}' used!")

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

        if coerce is None:
            return parsed

        if coerce == "int":
            parsed = int(parsed)
        elif coerce == "float":
            parsed = float(parsed)
        else:
            raise ValueError("Unsupported target type to coerce!")

        return parsed

    def parse_date(
            self, val: str, fmt: str, dst_fmt: str = None, coerce: str = None,
            errors: str = "raise") -> Union[str, date, datetime]:
        """
        Parse a date string.

        Params:
        -------
        val:
            Value to parse.

        fmt:
            String that defines the format of the input date.

        dst_fmt:
            String that controls the resulting date format. \n
            If `None` is used (default), then no final formatting \n
            will be applied and the result defined by 'target_type' \n
            parameter will be returned.

        coerce:
            Resulting data type:
            - None: The result of parsing will be converted to a "datetime.datetime" object.
            - "date": The result of parsing will be converted to a "datetime.date" object.

        errors:
            Action to take if an error is encountered durig parsing:
            - 'raise': Exceptions will be raised.
            - 'ignore': Exceptions won't be raised and the original input value will be returned.

        Raises:
        -------
        ValueError: If an invalid parameter value is passed.
        ParsingError: If parsing of the value fails.

        Returns:
        --------
        Parsed date if parsing succeeeds.
        The original string if parsing fails and "ignore_errors" is used.
        """

        if errors not in ["raise", "ignore"]:
            raise ValueError(f"Parameter 'errors' got an unrecognized value '{errors}'!")

        repl = val.replace(" ", "")

        try:
            parsed = datetime.strptime(repl, fmt)
        except Exception as exc:
            if errors == "raise":
                raise ParsingError(str(exc)) from exc
            if errors == "ignore":
                return val

        if coerce is None:
            res = parsed
        elif coerce == "date":
            res = parsed.date()
        else:
            raise ValueError("Unsupported target type to coerce!")

        if dst_fmt is None:
            return res

        try:
            formatted = parsed.strftime(dst_fmt)
        except Exception as exc:
            raise ValueError(
                "Could not format the parsed string! "
                f"The format '{dst_fmt}' is invalid."
            ) from exc

        return formatted

    def find_numbers(self, text: str, coerce = None, errors = "raise") -> list:
        """
        Find any numeric value in a text.

        Params:
        -------
        text:
            Text to scan.
            Any witespaces are removed before parsing.

        coerce:
            Indicates whether the pared number should
            be converted into a specific data type:
            - `None` (default): The data type of the found numeric strings will be inferred.
            - `int`: The found numeric strings will be converted to `int`.
            - `float`: The found numeric strings will be converted to `float`.
            - `str`: The found numeric strings won't be converted.

        errors:
            Action to take if an error is encountered durig parsing:
            - "raise": Exceptions will be raised.
            - "ignore": Any exceptions encuntered during conversion are ignored
                        and the unconverted numeric string will be added to the
                        resulting list.

        Returns:
        --------
        A list of numbers found, or an empty list if there's no match.
        """

        result = []
        nums = re.findall(r"[1-9][\d.,]+", text)

        for num in nums:
            parsed = self.parse_number(num, coerce, errors)
            result.append(parsed)

        return result
