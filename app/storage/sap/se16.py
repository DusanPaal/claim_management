"""
Represents operations done in SAP SE16
transaction in the process of claim creatin.
"""

from typing import Union
from . import rfc
from . import Invoice, Delivery

def find_notifications(doc: Union[Invoice, Delivery]) -> list:
    """Search for an existing service notification.

    Params:
    ------
    doc:
        Represents the document that serves as searching criteria:
        - instance of class `Invoice`: invoice issued by Ledvance.
        - instance of class `Delivery`: delivery note of an order shipped by Ledvance.

    Returns:
    --------
    List of notification ID numbers stored as int.
    """

    if isinstance(doc, Delivery):
        doc_field_name = "LS_VBELN"
    elif isinstance(doc, Invoice):
        doc_field_name = "ZZ_VBELN_VF"
    else:
        raise TypeError(f"Expected document with type 'Delivery' or 'Invoice', but got '{type(doc)}'!")

    doc_num = rfc.format_number(int(doc))

    query = f"{doc_field_name} = '{doc_num}' AND QMART EQ 'YZ'"

    response = rfc.RFC_READ_TABLE(
        rfc.connection,
        query_table = 'QMEL',
        options = [{'TEXT': query}],
        fields = [
            {'FIELDNAME': 'QMNUM'},
            {'FIELDNAME': 'FIN_CUSTDISP_AMT'},
            {'FIELDNAME': 'CATEGORY'},
        ],
        data_format = "structured"
    )

    notifs = [int(rec['QMNUM']) for rec in response['DATA']]

    return notifs

def get_shipping_point(doc: Delivery) -> str:
    """Returns a shipping point associated with a delivery note."""

    # TODO: if the priority is really needed, then make
    # this procedure a more generic function

    if not isinstance(doc, Delivery):
        raise TypeError(f"An instance of class 'Delivery' expected, but got '{type(doc)}'!")

    doc_num = rfc.format_number(int(doc))
    query = f"VBELN = '{doc_num}'"

    response = rfc.RFC_READ_TABLE(
        rfc.connection,
        query_table = 'LIKP',
        options = [{'TEXT': query}],
        fields = [{'FIELDNAME': 'VSTEL'}],
        data_format = "structured"
    )

    return response["DATA"][0]["VSTEL"]
