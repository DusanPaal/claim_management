"""Interface for performing operations on SAP backend using RFC."""

import os
import sys
from os.path import join
from pprint import PrettyPrinter
from typing import Union
from datetime import datetime
from ... import logger
import re

try:
    from pyrfc import (
        ABAPApplicationError, ABAPRuntimeError,
        CommunicationError, Connection, LogonError
    )
except:
    pass

pp = PrettyPrinter(indent=4)
g_log = logger.get_global_logger()
connection = None

class NotificationInProcessWarning(Warning):
    """Attempt to release a notification that is already in process."""

class CaseLockedError(Exception):
    """Attempt to modify a case that is being processed by a user."""

class NotificationDeletedError(Exception):
    """Attempt to modify a notification having a deletion flag."""

class NotificationLockedError(Exception):
    """Attempt to modify a notification that is being processed by a user."""

class NotificationDoesNotExistError(Exception):
    """Attempt to modify a notification that has not yet been created."""

def BAPI_DISPUTE_GETDETAIL_MULTI(conn, case_guid: str, print_data = False):
    '''FSCM-DM: Get Attributes of Dispute Case

    Parameters
    ----------
    case_guid : str
    *   Conversion table SCMG_T_CASE_ATTR Insert Case-ID into EXT_KEY and get CASE_GUID

    Returns
    -------
    result : dict
    *   Dispute with fields

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # case_detail =                                 {'CASE_GUID': case_guid}

    # TABLES:
    # ----
    # SCMG_T_CASE_ATTR =                            Case Attributes

    try:
        case_detail = [{'CASE_GUID': case_guid}]

        result = conn.call('BAPI_DISPUTE_GETDETAIL_MULTI',
                            CASE_DETAIL = case_detail)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_DISPUTE_ATTRIBUTES_CHANGE(conn, case_guid: str, attributes: list, notes = [], print_data = False):
    '''Change Dispute Case Attributes

        EXPORTING
        ----------
        *   case_guid =                 " bapi_dispute_split-case_guid  FSCM-DM: GUID (Internal Key of Dispute Case)
        *   testrun =                   " bapi_dispute_flags-testrun  Switch to Simulation Session for Write BAPIs

        IMPORTING
        ----------
        *   return =                    " bapiret2      Return Parameter

        TABLES
        ----------
        *   attributes =                " bapi_dispute_attribute  FSCM-DM: Attribute Value
        *   notes =                     " bapi_dispute_note  FSCM-DM: Text Lines for Notes for Dispute Case
        *   filecontent =               " bapi_dispute_filecontent  FSCM-DM: File content for Dispute Attachment

        EXAMPLE params in function
        ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # case_guid =                       '000D3A206F061EDB97D27915EC88803B'
    # attributes =                      [{'ATTR_ID': 'ZZ_QMNUM', 'ATTR_VALUE': '111'},                  # Notification
    #                                    {'ATTR_ID': 'CATEGORY', 'ATTR_VALUE': '001'},                  # Category
    #                                    {'ATTR_ID': 'FIN_BUKRS', 'ATTR_VALUE': 'cc'},                  # Company Code
    #                                    {'ATTR_ID': 'EXT_REF', 'ATTR_VALUE': '123'},                   # External Reference
    #                                    {'ATTR_ID': 'CASE_TITLE', 'ATTR_VALUE': 'TEST_MG2'},           # Title
    #                                    {'ATTR_ID': 'PROCESSOR', 'ATTR_VALUE': 'G.ROBOT2'},            # Processor
    #                                    {'ATTR_ID': 'FIN_COORDINATOR', 'ATTR_VALUE': 'MARTIN.GLEZL'},  # Coordinator
    #                                    {'ATTR_ID': 'FIN_CUSTDISP_AMT', 'ATTR_VALUE': '1.00'},         # Customer Disputed
    #                                    {'ATTR_ID': 'FIN_CUSTDISP_CUR', 'ATTR_VALUE': 'EUR'},          # Currency
    #                                    {'ATTR_ID': 'ZZ_STAT_SL', 'ATTR_VALUE': 'RFC test 123'},       # Status Sales
    #                                    {'ATTR_ID': 'ZZ_ZENTRALE', 'ATTR_VALUE': '111'},               # Head Office
    #                                    {'ATTR_ID': 'ZZ_FILIALE', 'ATTR_VALUE': '111'},                # Branch
    #                                    {'ATTR_ID': 'FIN_CONTACT_NAME', 'ATTR_VALUE': '111'},          # Contact Person
    #                                    {'ATTR_ID': 'FIN_CONTACT_MAIL', 'ATTR_VALUE': '111'},          # E-mail
    #                                    {'ATTR_ID': 'STAT_ORDERNO', 'ATTR_VALUE': '02'},               # Status
    #                                    {'ATTR_ID': 'FIN_KUNNR', 'ATTR_VALUE': '111'},                 # Customer
    #                                    {'ATTR_ID': 'REASON_CODE', 'ATTR_VALUE': '1XX'},               # Reason
    #                                    {'ATTR_ID': 'CASE_TYPE', 'ATTR_VALUE': '0052'},                # Case Type
    #                                    {'ATTR_ID': 'ZZ_DATUM', 'ATTR_VALUE': '20000101'},             # Customer Contact Date
    #                                    {'ATTR_ID': 'RESPONSIBLE', 'ATTR_VALUE': 'G.ROBOT2'},          # Person Responsible
    #                                    {'ATTR_ID': 'PLAN_END_DATE', 'ATTR_VALUE': '20000101'},        # Planned Closed Date
    #                                    {'ATTR_ID': 'ZZ_ESCAL_LEVEL', 'ATTR_VALUE': '1'},              # Escalation Level
    #                                    {'ATTR_ID': 'ZZ_ESCAL_DATE', 'ATTR_VALUE': '20000101'},        # Escalation Date
    #                                    {'ATTR_ID': 'FIN_ROOT_CCODE', 'ATTR_VALUE': 'L14'} ,           # Root Cause Code
    #                                    {'ATTR_ID': 'ZZ_STAT_AC', 'ATTR_VALUE': 'AA'},                 # Status AC
    #                                    {'ATTR_ID': 'ZZ_ZUONR', 'ATTR_VALUE': '111'},                  # Assignment
    #                                    {'ATTR_ID': 'FIN_CONTACT_TEL', 'ATTR_VALUE': '111'},           # Telephone No.
    #                                    {'ATTR_ID': 'FIN_CONTACT_FAX', 'ATTR_VALUE': '111'},           # Fax No.
    #                                    {'ATTR_ID': 'FIN_CONTACT_FAXC', 'ATTR_VALUE': 'SK'},           # Country of Fax No.
    #
    # notes =                           [{'TEXT_LINE': 'this NOTE was made by RFC'}],

    try:
        if len(notes) > 0:
            result = conn.call('BAPI_DISPUTE_ATTRIBUTES_CHANGE',
                                CASE_GUID = case_guid,
                                ATTRIBUTES = attributes,
                                NOTES = notes)
        else:
            result = conn.call('BAPI_DISPUTE_ATTRIBUTES_CHANGE',
                                CASE_GUID = case_guid,
                                ATTRIBUTES = attributes)

        if result["RETURN"]["TYPE"] == "E":
            err_msg = result["RETURN"]["MESSAGE"]

            if err_msg == "Case is locked by user G.ROBOT_RFC and is display only":
                raise CaseLockedError(err_msg)

            raise RuntimeError(err_msg)

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_CASE_GETNOTES(conn, case_guid: str, print_data = False):
    '''FSCM-DM: Get Notes of Dispute Case

    Parameters
    ----------
    case_guid : str
    *   Conversion table SCMG_T_CASE_ATTR Insert Case-ID into EXT_KEY and get CASE_GUID

    Returns
    -------
    result : dict
    *   Dispute with note fields

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # case_guid =                                   '000D3A206F061EDB97D27915EC88803B'

    # TABLES:
    # ----
    # SCMG_T_CASE_ATTR =                            Case Attributes

    try:
        result = conn.call('BAPI_CASE_GETNOTES',
                           GUID = case_guid)

        if print_data:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_CASE_READLOG(conn, case_guid: str, print_data = False):
    '''FSCM-DM: Read case log entries of Dispute Case

    Parameters
    ----------
    case_guid : str
    *   Conversion table SCMG_T_CASE_ATTR Insert Case-ID into EXT_KEY and get CASE_GUID

    Returns
    -------
    result : dict
    *   Log entries

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # case_guid =                                   '000D3A206F061EDB97D27915EC88803B'

    # TABLES:
    # ----
    # SCMG_T_CASE_ATTR =                            Case Attributes

    try:
        result = conn.call('BAPI_CASE_READLOG',
                           GUID = case_guid)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_TRANSACTION_COMMIT(conn, print_data = False):

    try:
        result = conn.call('BAPI_TRANSACTION_COMMIT')

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def RFC_READ_TABLE(conn, query_table, delimiter = ' ', no_data = ' ', options = [], fields = [], data = [], rowskips = 0, rowcount = 0, data_format = 'raw', print_data = False):
    ''' Query SAP tables (transaction SE16)
        Parameters
        ----------
        query_table : str
        *   Query table similar as in transaction SE16

        delimiter : str
        *   Sign for indicating field limits in DATA
        *   Default value - SPACE

        no_data : str
        *   NO_DATA <> SPACE suppresses the output of field contents in DATA
        *   Only the definition of the table is provided in the parameter FIELDS
        *   Default value - SPACE

        options: list
        *   Selection criteria for reading table lines (similar as input parameters in SE16)
        *   E.g.: [{'TEXT': "EXT_KEY = '000010225682'"}]

        fields: list
        *   List of fields to be read
        *   E.g.: [{'FIELDNAME': 'CASE_GUID'},{'FIELDNAME':'EXT_KEY'}]

        data: list
        *   Contains the data read. Note that DATA is only filled if the parameter no_data is left blank!

        rowskips: int
        *   Start at row
        *   Default value - 0 (start at first row of table)

        rowcount: int
        *   Number of rows to be fetched
        *   Default value - 0 (one single row)
        *   Max value - 999999

        data_format: str
        *   Select - 'raw' / 'structured'
        *   Raw - 1 row equals 1 string including blanks
        *   Structured - 1 row = 1 dictionary {key(column labes): values(row values)}

        Returns
        -------
        result : dict
        *   Table data with column labels, field lengths and offsets

        EXAMPLE params + TIPS in function
        ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # query_table =                     'SCMG_T_CASE_ATTR'
    # options =                         [{'TEXT': "EXT_KEY = '000010225682'"}] or [{'TEXT': "EXT_KEY EQ '000010225682'"}]
    #                                   [{'TEXT': "VBELN IN ('0408118515', '0408118516', '0408118517')"}]
    #                                   [{'TEXT': "VBELN IN ('0408118515', '0408118516', '0408118517') AND FKART EQ 'YF2'"}]
    # fields =                          [{'FIELDNAME': 'CASE_GUID'},{'FIELDNAME':'EXT_KEY'}]
    # rowskips =                        0
    # rowcount =                        10

    # DOCS:
    # ----
    # BBP_RFC_READ_TABLE
    # BAPI_SALESORDER_GETLIST
    # BAPISDORDER_GETDETAILEDLIST

    # Tips for Querying SAP Data
    # ----
    # RFC or BAPI:                      - If you run into limitations using the RFC RFC_READ_TABLE,
    #                                     there are other options such as using the BAPI BBP_RFC_READ_TABLE or using a custom RFC.
    #                                   - The steps to use a BAPI or custom RFC are similar in Design Studio to the steps presented
    #                                     for the RFC RFC_READ_TABLE.
    # Row Limit:                        - The RFC RFC_READ_TABLE has a 512-character row limit.
    #                                   - That is, each row of data cannot exceed 512 characters.
    # Float:                            - The RFC RFC_READ_TABLE does not return any fields that contain a float datatype.
    #                                   - The BAPI BPP_RFC_READ_TABLE does not have this limitation.
    # ROWSKIPS and ROWCOUNT:            - The RFC RFC_READ_TABLE returns a maximum of 999999 records at once.
    #                                   - As this may exceed the limitations of the number of records that can be processed by an endpoint
    #                                     in a downstream operation, you may want to use the fields ROWSKIPS and ROWCOUNT to implement
    #                                     a form of chunking.
    # ROWSKIPS:                         - Is the beginning row number, and ROWCOUNT is the number of rows to fetch.
    #                                   - For example: ROWSKIPS = 0, ROWCOUNT = 500 fetches the first 500 records,
    #                                                  ROWSKIPS = 501, ROWCOUNT = 500 gets the next 500 records, and so on.
    #                                   - If left at 0, then no chunking is implemented.
    #                                   - The maximum value for either of these fields is 999999.
    # OPTION:                           - The OPTION field holds the query condition.
    #                                   - There is a 75-character limit to the length of the query, so if the query exceeds that limit,
    #                                     additional folders must be created to hold the entire query string.
    # Error Handling:                   - The RFC RFC_READ_TABLE does not return error messages.
    #                                   - Errors when using the BAPI BPP_RFC_READ_TABLE are returned through the SAP Connector:
    #
    #                                     If the table name is invalid:
    #
    #                                     (126) TABLE_NOT_AVAILABLE: TABLE_NOT_AVAILABLE Message 029 of class SV type E, Par[1]: DD5T
    #                                     If there is an invalid condition:
    #
    #                                     JCO_ERROR_SYSTEM_FAILURE: A condition specified dynamically has an unexpected format.
    #                                     If a field name is invalid:
    #
    #                                     (126) FIELD_NOT_VALID: FIELD_NOT_VALID
    #                                     Views: Creating views in SAP can be helpful for dealing with joined tables.
    # Query Operators:                  - The SAP query language uses these operators:
    #                                     EQ	equal to
    #                                     NE	not equal to
    #                                     LT	less than
    #                                     LE	less than or equal to
    #                                     GT	greater than
    #                                     GE	greater than or equal to
    #                                     LIKE	as in LIKE `Emma%`
    #                                     IN    multiple values in tuple

    try:
        result = conn.call('RFC_READ_TABLE',
                            QUERY_TABLE = query_table,
                            DELIMITER = delimiter,
                            NO_DATA = no_data,
                            ROWSKIPS = rowskips,
                            ROWCOUNT = rowcount,
                            OPTIONS = options,
                            FIELDS = fields,
                            DATA = data
                            )

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError) as exc:
        print(f"An error occurred: {exc}")
        raise

    if data_format == 'raw':
        result = result

    elif data_format == 'structured':

        dict_data = {}
        list_data = []

        for row in result['DATA']:

            dict_data = {}

            for field in result['FIELDS']:
                start = int(field['OFFSET'])
                end = int(field['OFFSET']) + int(field['LENGTH'])

                dict_data.update({field['FIELDNAME']: row['WA'][start:end].strip()})

            list_data.append(dict_data)

        result['DATA'] = list_data

    if print_data == True:
        pp.pprint(result['DATA'])

    return result

def BBP_RFC_READ_TABLE(conn, query_table, delimiter = ' ', no_data = ' ', options = [], fields = [], data = [], rowskips = 0, rowcount = 0, data_format = 'raw', print_data = False):
    ''' Query SAP tables (transaction SE16)
        Parameters
        ----------
        query_table : str
        *   Query table similar as in transaction SE16

        delimiter : str
        *   Sign for indicating field limits in DATA
        *   Default value - SPACE

        no_data : str
        *   NO_DATA <> SPACE suppresses the output of field contents in DATA
        *   Only the definition of the table is provided in the parameter FIELDS
        *   Default value - SPACE

        options: list
        *   Selection criteria for reading table lines (similar as input parameters in SE16)
        *   E.g.: [{'TEXT': "EXT_KEY = '000010225682'"}]

        fields: list
        *   List of fields to be read
        *   E.g.: [{'FIELDNAME': 'CASE_GUID'},{'FIELDNAME':'EXT_KEY'}]

        data: list
        *   Contains the data read. Note that DATA is only filled if the parameter no_data is left blank!

        rowskips: int
        *   Start at row
        *   Default value - 0 (start at first row of table)

        rowcount: int
        *   Number of rows to be fetched
        *   Default value - 0 (one single row)
        *   Max value - 999999

        data_format: str
        *   Select - 'raw' / 'structured'
        *   Raw - 1 row equals 1 string including blanks
        *   Structured - 1 row = 1 dictionary {key(column labes): values(row values)}

        Returns
        -------
        result : dict
        *   Table data with column labels, field lengths and offsets

        EXAMPLE params + TIPS in function
        ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # query_table =                     'SCMG_T_CASE_ATTR'
    # options =                         [{'TEXT': "EXT_KEY = '000010225682'"}] or [{'TEXT': "EXT_KEY EQ '000010225682'"}]
    #                                   [{'TEXT': "VBELN IN ('0408118515', '0408118516', '0408118517')"}]
    #                                   [{'TEXT': "VBELN IN ('0408118515', '0408118516', '0408118517') AND FKART EQ 'YF2'"}]
    # fields =                          [{'FIELDNAME': 'CASE_GUID'},{'FIELDNAME':'EXT_KEY'}]
    # rowskips =                        0
    # rowcount =                        10

    # DOCS:
    # ----
    # BBP_RFC_READ_TABLE
    # BAPI_SALESORDER_GETLIST
    # BAPISDORDER_GETDETAILEDLIST

    # Tips for Querying SAP Data
    # ----
    # RFC or BAPI:                      - If you run into limitations using the RFC RFC_READ_TABLE,
    #                                     there are other options such as using the BAPI BBP_RFC_READ_TABLE or using a custom RFC.
    #                                   - The steps to use a BAPI or custom RFC are similar in Design Studio to the steps presented
    #                                     for the RFC RFC_READ_TABLE.
    # Row Limit:                        - The RFC RFC_READ_TABLE has a 512-character row limit.
    #                                   - That is, each row of data cannot exceed 512 characters.
    # Float:                            - The RFC RFC_READ_TABLE does not return any fields that contain a float datatype.
    #                                   - The BAPI BPP_RFC_READ_TABLE does not have this limitation.
    # ROWSKIPS and ROWCOUNT:            - The RFC RFC_READ_TABLE returns a maximum of 999999 records at once.
    #                                   - As this may exceed the limitations of the number of records that can be processed by an endpoint
    #                                     in a downstream operation, you may want to use the fields ROWSKIPS and ROWCOUNT to implement
    #                                     a form of chunking.
    # ROWSKIPS:                         - Is the beginning row number, and ROWCOUNT is the number of rows to fetch.
    #                                   - For example: ROWSKIPS = 0, ROWCOUNT = 500 fetches the first 500 records,
    #                                                  ROWSKIPS = 501, ROWCOUNT = 500 gets the next 500 records, and so on.
    #                                   - If left at 0, then no chunking is implemented.
    #                                   - The maximum value for either of these fields is 999999.
    # OPTION:                           - The OPTION field holds the query condition.
    #                                   - There is a 75-character limit to the length of the query, so if the query exceeds that limit,
    #                                     additional folders must be created to hold the entire query string.
    # Error Handling:                   - The RFC RFC_READ_TABLE does not return error messages.
    #                                   - Errors when using the BAPI BPP_RFC_READ_TABLE are returned through the SAP Connector:
    #
    #                                     If the table name is invalid:
    #
    #                                     (126) TABLE_NOT_AVAILABLE: TABLE_NOT_AVAILABLE Message 029 of class SV type E, Par[1]: DD5T
    #                                     If there is an invalid condition:
    #
    #                                     JCO_ERROR_SYSTEM_FAILURE: A condition specified dynamically has an unexpected format.
    #                                     If a field name is invalid:
    #
    #                                     (126) FIELD_NOT_VALID: FIELD_NOT_VALID
    #                                     Views: Creating views in SAP can be helpful for dealing with joined tables.
    # Query Operators:                  - The SAP query language uses these operators:
    #                                     EQ	equal to
    #                                     NE	not equal to
    #                                     LT	less than
    #                                     LE	less than or equal to
    #                                     GT	greater than
    #                                     GE	greater than or equal to
    #                                     LIKE	as in LIKE `Emma%`
    #                                     IN    multiple values in tuple

    try:
        result = conn.call('BBP_RFC_READ_TABLE',
                            QUERY_TABLE = query_table,
                            DELIMITER = delimiter,
                            NO_DATA = no_data,
                            ROWSKIPS = rowskips,
                            ROWCOUNT = rowcount,
                            OPTIONS = options,
                            FIELDS = fields,
                            DATA = data
                            )

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    if data_format == 'raw':
        result = result

    elif data_format == 'structured':

        dict_data = {}
        list_data = []

        for row in result['DATA']:

            for field in result['FIELDS']:
                start = int(field['OFFSET'])
                end = int(field['OFFSET']) + int(field['LENGTH'])

                dict_data.update({field['FIELDNAME']: row['WA'][start:end].strip()})

            list_data.append(dict_data)

        result['DATA'] = list_data

    if print_data == True:
        pp.pprint(result['DATA'])

    return result

def RFC_FUNCTION_DESCRIPTION(conn, func_name):
    '''consult the RFC description and needed input fields

    Parameters
    ----------
    dict_sap_con : dict
        key to create connection with SAP, must contain: user, passwd, ashost, sysnr, client
    func_name : str
        name of the function that you want to verify

    Returns
    -------
    funct_desc : pyrfc.pyrfc.FunctionDescription
        RFC functional description object
    '''
    try:
        result = conn.get_function_description(func_name)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def GET_RFC_PARAMETERS(conn, func_name):
    '''create a list with the fields that the RFC need to insert data and the respective data types

    Parameters
    ----------
    dict_sap_con : dict
        key to create connection with SAP, must contain: user, passwd, ashost, sysnr, client
    func_name : str
        name of the function that you want to verify

    Returns
    -------
    lst_res : list
        list of dictionaries with field names and data types used in RFC
    '''

    try:
        result = conn.get_function_description(func_name)
        list_results = []

        for field in result.parameters[0]['type_description'].fields:
            dict_return = {'name': field['name'],'field_type': field['field_type']}
            list_results.append(dict_return)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return list_results


def GOS_API_GET_ATTA_LIST(conn, is_object = {}, print_data = False):
    '''Read attachment list of BOR (Business Object Repository)

    Parameters
    ----------
    is_object : dict
        Local Persistent Object Reference - BOR Compatible Structure and data
        {'INSTID': '000D3A206F061EDB97D27915EC88803B', 'TYPEID':'SCASE', 'CATID': 'BO'}

    Returns
    -------
    result : list
        list of dictionaries with field names and data types used in RFC
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # is_object =                       {'INSTID': '000D3A206F061EDB97D27915EC88803B', 'TYPEID':'SCASE', 'CATID': 'BO'}

    # DOCS:
    # ----
    # get coll CASE_GUID from table SCMG_T_CASE_ATTR
    # inser into field INSTID_A in table SRGBTBREL

    try:
        result = conn.call('GOS_API_GET_ATTA_LIST',
                           IS_OBJECT = is_object
                          )

        if print_data:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def GOS_API_DELETE_AL_ITEM(conn, is_atta_key = {}, print_data = False):
    '''read attachment list of BOR (Business Object Repository)

    Parameters
    ----------
    is_object : dict
        Local Persistent Object Reference - BOR Compatible Structure and data
        {'INSTID': '000D3A206F061EDB97D27915EC88803B', 'TYPEID':'SCASE', 'CATID': 'BO'}


    Returns
    -------
    lst_res : list
        list of dictionaries with field names and data types used in RFC
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # is_object =                       {'INSTID': '000D3A206F061EDB97D27915EC88803B', 'TYPEID':'SCASE', 'CATID': 'BO'}

    # DOCS:
    # ----
    # get coll CASE_GUID from table SCMG_T_CASE_ATTR
    # inser into field INSTID_A in table SRGBTBREL

    try:
        result = conn.call('GOS_API_DELETE_AL_ITEM',
                           IS_ATTA_KEY = is_atta_key
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def GOS_API_GET_AL_ITEM(conn, is_atta_key = {}, print_data = False):
    '''read attachment list of BOR (Business Object Repository)

    Parameters
    ----------
    is_object : dict
        Local Persistent Object Reference - BOR Compatible Structure and data
        {'INSTID': '000D3A206F061EDB97D27915EC88803B', 'TYPEID':'SCASE', 'CATID': 'BO'}


    Returns
    -------
    lst_res : list
        list of dictionaries with field names and data types used in RFC
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # is_object =                       {'INSTID': '000D3A206F061EDB97D27915EC88803B', 'TYPEID':'SCASE', 'CATID': 'BO'}

    # DOCS:
    # ----
    # get coll CASE_GUID from table SCMG_T_CASE_ATTR
    # inser into field INSTID_A in table SRGBTBREL

    try:
        result = conn.call('GOS_API_GET_AL_ITEM',
                           IS_ATTA_KEY = is_atta_key
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def GOS_API_INSERT_AL_ITEM(conn, is_attcont = {}, print_data = False):
    '''read attachment list of BOR (Business Object Repository)

    Parameters
    ----------
    is_object : dict
        Local Persistent Object Reference - BOR Compatible Structure and data
        {'INSTID': '000D3A206F061EDB97D27915EC88803B', 'TYPEID':'SCASE', 'CATID': 'BO'}


    Returns
    -------
    lst_res : list
        list of dictionaries with field names and data types used in RFC
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # is_object =                       {'INSTID': '000D3A206F061EDB97D27915EC88803B', 'TYPEID':'SCASE', 'CATID': 'BO'}

    # DOCS:
    # ----
    # get coll CASE_GUID from table SCMG_T_CASE_ATTR
    # inser into field INSTID_A in table SRGBTBREL

    try:
        result = conn.call('GOS_API_INSERT_AL_ITEM',
                           IS_ATTCONT = is_attcont
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SO_FOLDER_ROOT_ID_GET(conn, owner = '', region = '', print_data = False):
    '''Find the ID of a root folder (personal or general storage)

    Parameters
    ----------
    owner : string
        Owner of folders
        Default value - SPACE

    region : string
        Folder part (private or shared folders)
        Default value - 'Q'

    Returns
    -------
    folder ID
    '''

    try:
        result = conn.call('SO_FOLDER_ROOT_ID_GET',
                           OWNER = owner,
                           REGION = region
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SO_DOCUMENT_READ_API1(conn, document_id = '', print_data = False):
    '''SAPoffice: View object from folder using RFC

    Parameters
    ----------
    document_id : str
        ID of folder entry to be viewed
        document_id = 'FOL26000000000004EXT46000000025700'

    Returns
    -------
    lst_res : list
        list of dictionaries with field names and data types used in RFC
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # document_id =                     'FOL26000000000004EXT46000000025700'

    # DOCS:
    # ----
    # get coll CASE_GUID from table SCMG_T_CASE_ATTR
    # inser into field INSTID_A in table SRGBTBREL

    try:
        result = conn.call('SO_DOCUMENT_READ_API1',
                           DOCUMENT_ID = document_id
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SO_DOCUMENT_INSERT_API1(conn, file_path, obj_descr = '', folder_id = 'FOL26000000000004',  document_data = {}, document_type = '', object_header = [], contents_hex = [], print_data = False):
    '''SAPoffice: Create new office document using RFC

    Parameters
    ----------
    file_path : str
    *   full path to file to be uploaded to application server

    obj_descr : str
    *   Name of file to be displayed in SAP GOS
    *   Default value - name from file_path

    folder_id: str
    *   ID of folder in which document is to be created
    *   Call SO_FOLDER_ROOT_ID_GET

    document_data: dict
    *   Document attributes (general header)
    *   Type - SODOCCHGI1

    document_type: str
    *   SAP document class - EXT / BIN / TXT / PDF / DOC / XLS
    *   Default value - extention from file_path

    object_header: list
    *   Header data for document (spec.header)

    contents_hex: list
    *   Byte stream of binary file from file_path

    Returns
    -------
    result : dict
    *   Dictionary of import parameters
    *   File uploaded to SAP application server
    *   Call BINARY_RELATION_CREATE_COMMIT to allocate file to SAP BO (Business object)

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # folder_id =                               'FOL26000000000004',
    # document_data =                           {
    #                                            'OBJ_NAME': 'MESSAGE',
    #                                            'OBJ_DESCR': 'TEST_UPLOAD_RFC_21',
    #                                            'OBJ_LANGU': 'EN',
    #                                            'OBJ_SORT': '',
    #                                            'OBJ_EXPDAT': '',
    #                                            'SENSITIVTY': 'O',
    #                                            'OBJ_PRIO': '5',
    #                                            'NO_CHANGE': '',
    #                                            'PRIORITY': '5',
    #                                            'EXPIRY_DAT': '',
    #                                            'PROC_TYPE': '',
    #                                            'PROC_NAME': '',
    #                                            'PROC_SYST': '',
    #                                            'PROC_CLINT': '',
    #                                            'SKIP_SCREN': '',
    #                                            'TO_DO_OUT': '',
    #                                            'FREE_DEL': '',
    #                                            'DOC_SIZE': str(doc_size)
    #                                           },
    # document_type =                           'EXT',  # EXT / BIN / TXT (native editor)
    # object_header =                           [{'LINE': f"&SO_FILENAME=TEST_UPLOAD_RFC_21{doc_ext}"},
    #                                            {'LINE': '&SO_FORMAT=BIN'}, # {'LINE': '&SO_FORMAT=ASC'},
    #                                          # {'LINE': '&SO_CONTTYPE=application/pdf'} {'LINE': '&SO_CONTTYPE=text/plain'}
    #                                           ],
    # contents_hex =                            byte_con

    # Load file_path as binary a convert to bytes
    file = open(file_path, "rb")

    byte_con = []
    byte_len = 255
    byte_s = 0
    byte_e = byte_len
    byte = file.read()

    for i in range(int(len(byte) / byte_e + 1)):
        byte_con.append({'LINE': byte[byte_s: byte_e]})
        byte_s = byte_e
        byte_e = byte_e + byte_len

    file.close()

    # Get file specifications
    doc_size = os.path.getsize(file_path)
    doc_ext = os.path.splitext(file_path)[1]
    doc_type = doc_ext[1:][:3].upper()

    # Use file name for OBJ_DESCR parameter if NOT provided
    if obj_descr == '':
        obj_descr = os.path.basename(os.path.splitext(file_path)[0])

    # Default import attributes if NOT provided
    if document_data == {}:
        document_data = {'OBJ_NAME': 'MESSAGE',
                        'OBJ_DESCR': obj_descr,
                        'OBJ_LANGU': 'EN',
                        'OBJ_SORT': '',
                        'OBJ_EXPDAT': '',
                        'SENSITIVTY': 'O',
                        'OBJ_PRIO': '5',
                        'NO_CHANGE': '',
                        'PRIORITY': '5',
                        'EXPIRY_DAT': '',
                        'PROC_TYPE': '',
                        'PROC_NAME': '',
                        'PROC_SYST': '',
                        'PROC_CLINT': '',
                        'SKIP_SCREN': '',
                        'TO_DO_OUT': '',
                        'FREE_DEL': '',
                        'DOC_SIZE': str(doc_size)
                        }

    if document_type == '':
        document_type = doc_type   # EXT / BIN / TXT / PDF / DOC / XLS

    if object_header == []:
        object_header = [{'LINE': f"&SO_FILENAME={obj_descr}{doc_ext}"},
                         {'LINE': '&SO_FORMAT=BIN'}, # {'LINE': '&SO_FORMAT=ASC'},
                        ]

    if contents_hex == []:
        contents_hex = byte_con

    try:
        result = conn.call('SO_DOCUMENT_INSERT_API1',
                           FOLDER_ID = folder_id,
                           DOCUMENT_DATA = document_data,
                           DOCUMENT_TYPE = document_type,
                           OBJECT_HEADER = object_header,
                           CONTENTS_HEX = contents_hex
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SO_DOCUMENT_DELETE_API1(conn, document_id = '', print_data = False):
    '''Object relationship binary links

    Parameters
    ----------
    obj_rolea : dict
    *   SAP BO (Business object) - dispute, purchase order, sales order, invoice
    *   Reference table SRGBTBREL (transaction: SE16) e.g.: {'OBJKEY': coll (INSTID_A), 'OBJTYPE': coll (TYPEID_A), 'LOGSYS': ''}

    obj_roleb : dict
    *   File uploaded from SO_DOCUMENT_INSERT_API1
    *   Reference ['DOCUMENT_INFO'] e.g.: {'OBJKEY': ['DOCUMENT_INFO']['DOC_ID'], 'OBJTYPE': ['DOCUMENT_INFO']['OBJ_NAME'], 'LOGSYS': ''}

    relationtype: str
    *   Default value - 'ATTA'

    Returns
    -------
    result : dict
    *   BINREL

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # obj_rolea =                                   {'OBJKEY': '000D3A206F061EDB97D27915EC88803B',
    #                                                'OBJTYPE': 'SCASE',
    #                                                'LOGSYS': ''
    #                                               },
    # obj_roleb =                                   {'OBJKEY': message3['DOCUMENT_INFO']['DOC_ID'],
    #                                                'OBJTYPE': 'MESSAGE',
    #                                                'LOGSYS': ''
    #                                               },
    # relationtype =                                'ATTA'

    # DOCS:
    # ----
    # UDM_DISPUTE                                   - Conversion table SCMG_T_CASE_ATTR Insert Case-ID into EXT_KEY and get CASE_GUID
    #                                               - 'OBJKEY': CASE_GUID
    #                                               - 'OBJTYPE': 'SCASE'
    # Sales Order (YTA)                             - 'OBJTYPE': 'BUS2032'
    # Credit Note                                   - 'OBJTYPE': 'BUS2094'
    # Debit Memo                                    - 'OBJTYPE': 'BUS2096'
    # Returns                                       - 'OBJTYPE': 'BUS2102'
    # Invoice                                       - 'OBJTYPE': 'BKPF'
    # Delivery Note                                 - 'OBJTYPE': 'LIKP'
    # Quality Notification                          - 'OBJTYPE': 'QMSM'


    # TABLES:
    # ----
    # SRGBTBREL                                     - SAP Relationships in GOS Environment Table and data

    try:
        result = conn.call('SO_DOCUMENT_DELETE_API1',
                           DOCUMENT_ID = document_id
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result


def BINARY_RELATION_CREATE_COMMIT(conn, obj_rolea = {}, obj_roleb = {}, relationtype = 'ATTA', print_data = False):
    '''Object relationship binary links

    Parameters
    ----------
    obj_rolea : dict
    *   SAP BO (Business object) - dispute, purchase order, sales order, invoice
    *   Reference table SRGBTBREL (transaction: SE16) e.g.: {'OBJKEY': coll (INSTID_A), 'OBJTYPE': coll (TYPEID_A), 'LOGSYS': ''}

    obj_roleb : dict
    *   File uploaded from SO_DOCUMENT_INSERT_API1
    *   Reference ['DOCUMENT_INFO'] e.g.: {'OBJKEY': ['DOCUMENT_INFO']['DOC_ID'], 'OBJTYPE': ['DOCUMENT_INFO']['OBJ_NAME'], 'LOGSYS': ''}

    relationtype: str
    *   Default value - 'ATTA'

    Returns
    -------
    result : dict
    *   BINREL

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # Add attachment to Dispute Case
    # ------------------------------
    # obj_rolea =                                   {'OBJKEY': '000D3A206F061EDB97D27915EC88803B',
    #                                                'OBJTYPE': 'SCASE',
    #                                                'LOGSYS': ''
    #                                               },
    # obj_roleb =                                   {'OBJKEY': message3['DOCUMENT_INFO']['DOC_ID'],
    #                                                'OBJTYPE': 'MESSAGE',
    #                                                'LOGSYS': ''
    #                                               },
    # relationtype =                                'ATTA'
    #
    # Reference next/preceeding document in QM01
    # ------------------------------
    # obj_rolea =                                   {'OBJKEY': 001001279784,            QM
    #                                               'OBJTYPE': 'BUS2078',
    #                                               'LOGSYS': 'Q25_050'
    #                                               },
    # obj_roleb =                                   {'OBJKEY': 000010226074,            Dispute Case (UMD_DISPUTE)
    #                                               'OBJTYPE': 'BUS2022',
    #                                               'LOGSYS': 'Q25_050'
    #                                               },
    # relationtype =                                'FWUP'                              VORGAENGER -> NACHFOLGER
    #
    # Object types:
    # ----
    # Dispute (UDM_DISPUTE)                         - Conversion table SCMG_T_CASE_ATTR Insert Case-ID into EXT_KEY and get CASE_GUID
    #                                               - 'OBJKEY': CASE_GUID
    #                                               - 'OBJTYPE': 'SCASE'
    # Sales Order (VA03)                            - 'OBJTYPE': 'BUS2032'
    # Billing Document (VF03)                       - 'OBJTYPE': 'VBRK'
    # Schedule Agreement (VA33)                     - 'OBJTYPE': 'BUS2035'
    # Dispute Case                                  - 'OBJTYPE': 'BUS2022'
    # Credit Memo Request                           - 'OBJTYPE': 'BUS2094'
    # Debit Memo                                    - 'OBJTYPE': 'BUS2096'
    # Returns                                       - 'OBJTYPE': 'BUS2102'
    # Quality Notification                          - 'OBJTYPE': 'BUS2078'
    # Service Notification                          - 'OBJTYPE': 'BUS2080'


    # TABLES:
    # ----
    # SRGBTBREL                                     - SAP Relationships in GOS Environment Table and data
    # ORBRELTYP                                     - SAP relationship types Role A, Role B, Relation
    # OROBJROLES                                    - SAP object roles (NACHFOLGER)

    try:
        result = conn.call('BINARY_RELATION_CREATE_COMMIT',
                           OBJ_ROLEA = obj_rolea,
                           OBJ_ROLEB = obj_roleb,
                           RELATIONTYPE = relationtype,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BINARY_RELATION_DELETE_COMMIT(conn, obj_rolea = {}, obj_roleb = {}, relationtype = 'ATTA', print_data = False):
    '''Object relationship binary links

    Parameters
    ----------
    obj_rolea : dict
    *   SAP BO (Business object) - dispute, purchase order, sales order, invoice
    *   Reference table SRGBTBREL (transaction: SE16) e.g.: {'OBJKEY': coll (INSTID_A), 'OBJTYPE': coll (TYPEID_A), 'LOGSYS': ''}

    obj_roleb : dict
    *   File uploaded from SO_DOCUMENT_INSERT_API1
    *   Reference ['DOCUMENT_INFO'] e.g.: {'OBJKEY': ['DOCUMENT_INFO']['DOC_ID'], 'OBJTYPE': ['DOCUMENT_INFO']['OBJ_NAME'], 'LOGSYS': ''}

    relationtype: str
    *   Default value - 'ATTA'

    Returns
    -------
    result : dict
    *   BINREL

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # obj_rolea =                                   {'OBJKEY': '000D3A206F061EDB97D27915EC88803B',
    #                                                'OBJTYPE': 'SCASE',
    #                                                'LOGSYS': ''
    #                                               },
    # obj_roleb =                                   {'OBJKEY': message3['DOCUMENT_INFO']['DOC_ID'],
    #                                                'OBJTYPE': 'MESSAGE',
    #                                                'LOGSYS': ''
    #                                               },
    # relationtype =                                'ATTA'

    # DOCS:
    # ----
    # UDM_DISPUTE                                   - Conversion table SCMG_T_CASE_ATTR Insert Case-ID into EXT_KEY and get CASE_GUID
    #                                               - 'OBJKEY': CASE_GUID
    #                                               - 'OBJTYPE': 'SCASE'
    # Sales Order (YTA)                             - 'OBJTYPE': 'BUS2032'
    # Credit Note                                   - 'OBJTYPE': 'BUS2094'
    # Debit Memo                                    - 'OBJTYPE': 'BUS2096'
    # Returns                                       - 'OBJTYPE': 'BUS2102'
    # Invoice                                       - 'OBJTYPE': 'BKPF'
    # Delivery Note                                 - 'OBJTYPE': 'LIKP'
    # Quality Notification                          - 'OBJTYPE': 'QMSM'


    # TABLES:
    # ----
    # SRGBTBREL                                     - SAP Relationships in GOS Environment Table and data

    try:
        result = conn.call('BINARY_RELATION_DELETE_COMMIT',
                           OBJ_ROLEA = obj_rolea,
                           OBJ_ROLEB = obj_roleb,
                           RELATIONTYPE = relationtype,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_MATERIAL_GET_ALL(conn, material = '', salesorg = '', distr_chan = '', plant = '', print_data = False):
    '''Object relationship binary links

    Parameters
    ----------
    obj_rolea : dict
    *   SAP BO (Business object) - dispute, purchase order, sales order, invoice
    *   Reference table SRGBTBREL (transaction: SE16) e.g.: {'OBJKEY': coll (INSTID_A), 'OBJTYPE': coll (TYPEID_A), 'LOGSYS': ''}

    obj_roleb : dict
    *   File uploaded from SO_DOCUMENT_INSERT_API1
    *   Reference ['DOCUMENT_INFO'] e.g.: {'OBJKEY': ['DOCUMENT_INFO']['DOC_ID'], 'OBJTYPE': ['DOCUMENT_INFO']['OBJ_NAME'], 'LOGSYS': ''}

    relationtype: str
    *   Default value - 'ATTA'

    Returns
    -------
    result : dict
    *   BINREL

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # material =                                   101226950100

    # DOCS:
    # ----

    # TABLES:
    # ----
    # STXH / STXL                                   - Basic Data Text

    try:
        result = conn.call('BAPI_MATERIAL_GET_ALL',
                           MATERIAL = material,
                           SALESORG = salesorg,
                           DISTR_CHAN = distr_chan,
                           PLANT = plant,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_MATERIAL_SAVEDATA(conn, headdata = {}, clientdata = {}, clientdatax = {}, plantdata = {}, plantdatax = {}, forecastparameters = {}, forecastparametersx = {}, planningdata = {}, planningdatax = {},
                           storagelocationdata = {}, storagelocationdatax = {}, valuationdata = {}, valuationdatax = {}, warehousenumberdata = {}, warehousenumberdatax = {}, salesdata = {}, salesdatax = {},
                           storagetypedata = {}, storagetypedatax = {}, flag_online = '', flag_cad_call = '', no_dequeue = '', no_rollback_work  = '', materialdescription = [], unitsofmeasure = [], unitsofmeasurex = [],
                           internationalartnos = [], materiallongtext = [], taxclassifications = [], returnmessages = [], prtdata = [], prtdatax = [], extensionin = [], extensioninx = [], print_data = False):

    '''Create and Change Material Master Data

    Parameters
    ----------
    headdata : dict
    *   Header segment with control information
    *   The fields essentially correspond to the fields available on the initial screen in dialog maintenance
        when creating a material master record

    clientdata : dict
    *   Client-specific material data

    clientdatax : dict
    *   Information on update for CLIENTDATA

    Returns
    -------
    result : dict
    *   Dictionary of import parameters
    *   File uploaded to SAP application server
    *   Call BINARY_RELATION_CREATE_COMMIT to allocate file to SAP BO (Business object)

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # case_guid =                       '000D3A206F061EDB97D27915EC88803B'
    # attributes =                      [{'ATTR_ID': 'ZZ_QMNUM', 'ATTR_VALUE': '111'},                  # Notification
    #                                    {'ATTR_ID': 'CATEGORY', 'ATTR_VALUE': '001'},                  # Category
    #                                    {'ATTR_ID': 'FIN_BUKRS', 'ATTR_VALUE': 'cc'},                  # Company Code
    #                                    {'ATTR_ID': 'EXT_REF', 'ATTR_VALUE': '123'},                   # External Reference
    #                                    {'ATTR_ID': 'CASE_TITLE', 'ATTR_VALUE': 'TEST_MG2'},           # Title
    #                                    {'ATTR_ID': 'PROCESSOR', 'ATTR_VALUE': 'G.ROBOT2'},            # Processor
    #                                    {'ATTR_ID': 'FIN_COORDINATOR', 'ATTR_VALUE': 'MARTIN.GLEZL'},  # Coordinator
    #                                    {'ATTR_ID': 'FIN_CUSTDISP_AMT', 'ATTR_VALUE': '1.00'},         # Customer Disputed
    #                                    {'ATTR_ID': 'FIN_CUSTDISP_CUR', 'ATTR_VALUE': 'EUR'},          # Currency
    #                                    {'ATTR_ID': 'ZZ_STAT_SL', 'ATTR_VALUE': 'RFC test 123'},       # Status Sales
    #                                    {'ATTR_ID': 'ZZ_ZENTRALE', 'ATTR_VALUE': '111'},               # Head Office
    #                                    {'ATTR_ID': 'ZZ_FILIALE', 'ATTR_VALUE': '111'},                # Branch
    #                                    {'ATTR_ID': 'FIN_CONTACT_NAME', 'ATTR_VALUE': '111'},          # Contact Person
    #                                    {'ATTR_ID': 'FIN_CONTACT_MAIL', 'ATTR_VALUE': '111'},          # E-mail
    #                                    {'ATTR_ID': 'STAT_ORDERNO', 'ATTR_VALUE': '02'},               # Status
    #                                    {'ATTR_ID': 'FIN_KUNNR', 'ATTR_VALUE': '111'},                 # Customer
    #                                    {'ATTR_ID': 'REASON_CODE', 'ATTR_VALUE': '1XX'},               # Reason
    #                                    {'ATTR_ID': 'CASE_TYPE', 'ATTR_VALUE': '0052'},                # Case Type
    #                                    {'ATTR_ID': 'ZZ_DATUM', 'ATTR_VALUE': '20000101'},             # Customer Contact Date
    #                                    {'ATTR_ID': 'RESPONSIBLE', 'ATTR_VALUE': 'G.ROBOT2'},          # Person Responsible
    #                                    {'ATTR_ID': 'PLAN_END_DATE', 'ATTR_VALUE': '20000101'},        # Planned Closed Date
    #                                    {'ATTR_ID': 'ZZ_ESCAL_LEVEL', 'ATTR_VALUE': '1'},              # Escalation Level
    #                                    {'ATTR_ID': 'ZZ_ESCAL_DATE', 'ATTR_VALUE': '20000101'},        # Escalation Date
    #                                    {'ATTR_ID': 'FIN_ROOT_CCODE', 'ATTR_VALUE': 'L14'} ,           # Root Cause Code
    #                                    {'ATTR_ID': 'ZZ_STAT_AC', 'ATTR_VALUE': 'AA'},                 # Status AC
    #                                    {'ATTR_ID': 'ZZ_ZUONR', 'ATTR_VALUE': '111'},                  # Assignment
    #                                    {'ATTR_ID': 'FIN_CONTACT_TEL', 'ATTR_VALUE': '111'},           # Telephone No.
    #                                    {'ATTR_ID': 'FIN_CONTACT_FAX', 'ATTR_VALUE': '111'},           # Fax No.
    #                                    {'ATTR_ID': 'FIN_CONTACT_FAXC', 'ATTR_VALUE': 'SK'},           # Country of Fax No.
    #
    # notes =                           [{'TEXT_LINE': 'this NOTE was made by RFC'}],

    try:
        result = conn.call('BAPI_MATERIAL_SAVEDATA',
                            HEADDATA = headdata,
                            CLIENTDATA = clientdata,
                            CLIENTDATAX = clientdatax,
                            PLANTDATA = plantdata,
                            PLANTDATAX = plantdatax,
                            FORECASTPARAMETERS = forecastparameters,
                            FORECASTPARAMETERSX = forecastparametersx,
                            PLANNINGDATA = planningdata,
                            PLANNINGDATAX = planningdatax,
                            STORAGELOCATIONDATA = storagelocationdata,
                            STORAGELOCATIONDATAX = storagelocationdatax,
                            VALUATIONDATA = valuationdata,
                            VALUATIONDATAX = valuationdatax,
                            WAREHOUSENUMBERDATA = warehousenumberdata,
                            WAREHOUSENUMBERDATAX = warehousenumberdatax,
                            SALESDATA = salesdata,
                            SALESDATAX = salesdatax,
                            STORAGETYPEDATA = storagetypedata,
                            STORAGETYPEDATAX = storagetypedatax,
                            FLAG_ONLINE = flag_online,
                            FLAG_CAD_CALL = flag_cad_call,
                            NO_DEQUEUE = no_dequeue,
                            NO_ROLLBACK_WORK = no_rollback_work,
                            MATERIALDESCRIPTION = materialdescription,
                            UNITSOFMEASURE = unitsofmeasure,
                            UNITSOFMEASUREX = unitsofmeasurex,
                            INTERNATIONALARTNOS = internationalartnos,
                            MATERIALLONGTEXT = materiallongtext,
                            TAXCLASSIFICATIONS = taxclassifications,
                            RETURNMESSAGES = returnmessages,
                            PRTDATA = prtdata,
                            PRTDATAX = prtdatax,
                            EXTENSIONIN = extensionin,
                            EXTENSIONINX = extensioninx,
                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def RFC_SAVE_TEXT(conn, text_lines = [], print_data = False):
    '''SAPScript create / change texts

    Parameters
    ----------
    text_lines : list
    *   IBIP: Long text line with logical key
    *   Structure: [{'MANDT': '', 'TDOBJECT': '', 'TDNAME': '', 'TDID': '', 'TDSPRAS': '', 'TDLINE': ''}]

    Returns
    -------
    result : dict
    *   Message with transferred input parameters

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # text_lines =                                  [{'MANDT': '059',
    #                                                 'TDOBJECT': 'MVKE',
    #                                                 'TDNAME': '000000101226950100',
    #                                                 'TDID': 'Z001',
    #                                                 'TDSPRAS': 'S',
    #                                                 'TDLINE': 'ROBOT TEXT TT 321'
    #                                               }]
    # MANDT =                                       - Client - 059 (C25) / 050 (Q25)

    # DOCS:
    # ----
    # Different text types require a unique         - Basic Data Text = [{'TDOBJECT': 'MATERIAL', 'TDID': 'GRUN'}]
    # combination of fields TDOBJECT and TDID       - Basic Data Text (Internal comment) = [{'TDOBJECT': 'MATERIAL', 'TDID': 'IVER'}]
    #                                               - Purchase Order Text = [{'TDOBJECT': 'MATERIAL', 'TDID': 'BEST'}]
    #                                               - Sales Text = [{'TDOBJECT': 'MVKE', 'TDID': '0001'}]
    #                                               - Tender Text = [{'TDOBJECT': 'MVKE', 'TDID': 'Z001'}]
    #
    # TABLES:
    # ----
    # STXH / STXL                                   - STXD SAPscript text file header

    try:
        result = conn.call('RFC_SAVE_TEXT',
                           TEXT_LINES = text_lines,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def RFC_READ_TEXT(conn, text_lines = [], print_data = False):
    '''SAPScript read texts

    Parameters
    ----------
    text_lines : list
    *   IBIP: Long text line with logical key
    *   Structure: [{'MANDT': '', 'TDOBJECT': '', 'TDNAME': '', 'TDID': '', 'TDSPRAS': '', 'TDLINE': ''}]

    Returns
    -------
    result : dict
    *   Message with transferred input parameters

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # text_lines =                                  [{'MANDT': '059',
    #                                                 'TDOBJECT': 'MVKE',
    #                                                 'TDNAME': '000000101226950100',
    #                                                 'TDID': 'Z001',
    #                                                 'TDSPRAS': 'S',
    #                                                 'TDLINE': ''
    #                                               }]
    # MANDT =                                       - Client - 059 (C25) / 050 (Q25)

    # DOCS:
    # ----
    # Different text types require a unique         - Basic Data Text = [{'TDOBJECT': 'MATERIAL', 'TDID': 'GRUN'}]
    # combination of fields TDOBJECT and TDID       - Basic Data Text (Internal comment) = [{'TDOBJECT': 'MATERIAL', 'TDID': 'IVER'}]
    #                                               - Purchase Order Text = [{'TDOBJECT': 'MATERIAL', 'TDID': 'BEST'}]
    #                                               - Sales Text = [{'TDOBJECT': 'MVKE', 'TDID': '0001'}]
    #                                               - Tender Text = [{'TDOBJECT': 'MVKE', 'TDID': 'Z001'}]
    #
    # TABLES:
    # ----
    # STXH / STXL                                   - STXD SAPscript text file header

    try:
        result = conn.call('RFC_READ_TEXT',
                           TEXT_LINES = text_lines,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def RFC_DELETE_TEXT(conn, text_lines = [], print_data = False):
    '''SAPScript delete texts

    Parameters
    ----------
    text_lines : list
    *   IBIP: Long text line with logical key
    *   Structure: [{'MANDT': '', 'TDOBJECT': '', 'TDNAME': '', 'TDID': '', 'TDSPRAS': '', 'TDLINE': ''}]

    Returns
    -------
    result : dict
    *   Message with transferred input parameters

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # text_lines =                                  [{'MANDT': '059',
    #                                                 'TDOBJECT': 'MVKE',
    #                                                 'TDNAME': '000000101226950100',
    #                                                 'TDID': 'Z001',
    #                                                 'TDSPRAS': 'S',
    #                                                 'TDLINE': ''
    #                                               }]
    # MANDT =                                       - Client - 059 (C25) / 050 (Q25)

    # DOCS:
    # ----
    # Different text types require a unique         - Basic Data Text = [{'TDOBJECT': 'MATERIAL', 'TDID': 'GRUN'}]
    # combination of fields TDOBJECT and TDID       - Basic Data Text (Internal comment) = [{'TDOBJECT': 'MATERIAL', 'TDID': 'IVER'}]
    #                                               - Purchase Order Text = [{'TDOBJECT': 'MATERIAL', 'TDID': 'BEST'}]
    #                                               - Sales Text = [{'TDOBJECT': 'MVKE', 'TDID': '0001'}]
    #                                               - Tender Text = [{'TDOBJECT': 'MVKE', 'TDID': 'Z001'}]
    #
    # TABLES:
    # ----
    # STXH / STXL                                   - STXD SAPscript text file header

    try:
        result = conn.call('RFC_DELETE_TEXT',
                           TEXTS = text_lines,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def RSAQ_REMOTE_QUERY_CALL(conn, workspace = '', query = '', usergroup = '', variant = '', dbacc = 0, skip_selscreen = 'X', data_to_memory = '', external_presentation = '',
                           selection_table = [], ldata = [], listdesc = [], fpairs = [], print_data = False):
    '''SAPScript delete texts

    Parameters
    ----------
    text_lines : list
    *   IBIP: Long text line with logical key
    *   Structure: [{'MANDT': '', 'TDOBJECT': '', 'TDNAME': '', 'TDID': '', 'TDSPRAS': '', 'TDLINE': ''}]

    Returns
    -------
    result : dict
    *   Message with transferred input parameters

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # text_lines =                                  [{'MANDT': '059',
    #                                                 'TDOBJECT': 'MVKE',
    #                                                 'TDNAME': '000000101226950100',
    #                                                 'TDID': 'Z001',
    #                                                 'TDSPRAS': 'S',
    #                                                 'TDLINE': ''
    #                                               }]
    # MANDT =                                       - Client - 059 (C25) / 050 (Q25)

    # DOCS:
    # ----
    # Different text types require a unique         - Basic Data Text = [{'TDOBJECT': 'MATERIAL', 'TDID': 'GRUN'}]
    # combination of fields TDOBJECT and TDID       - Basic Data Text (Internal comment) = [{'TDOBJECT': 'MATERIAL', 'TDID': 'IVER'}]
    #                                               - Purchase Order Text = [{'TDOBJECT': 'MATERIAL', 'TDID': 'BEST'}]
    #                                               - Sales Text = [{'TDOBJECT': 'MVKE', 'TDID': '0001'}]
    #                                               - Tender Text = [{'TDOBJECT': 'MVKE', 'TDID': 'Z001'}]
    #
    # TABLES:
    # ----
    # STXH / STXL                                   - STXD SAPscript text file header

    try:
        result = conn.call('RSAQ_REMOTE_QUERY_CALL',
                           WORKSPACE = workspace,
                           QUERY = query,
                           USERGROUP = usergroup,
                           VARIANT = variant,
                           DBACC = dbacc,
                           SKIP_SELSCREEN = skip_selscreen,
                           DATA_TO_MEMORY = data_to_memory,
                           EXTERNAL_PRESENTATION = external_presentation,
                           SELECTION_TABLE = selection_table,
                           LDATA = ldata,
                           LISTDESC = listdesc,
                           FPAIRS = fpairs,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def RFC_SYSTEM_INFO(conn, print_data = False):
    '''System information of SAP

    Returns
    -------
    result : dict
    *   Message with system information

    '''
    try:
        result = conn.call('RFC_SYSTEM_INFO')

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def RFC_GET_LOCAL_SERVERS(conn, print_data = False):
    '''Returns all currently active RFC destinations in the same database

    Returns
    -------
    result : dict
    *   Message with host information

    '''
    try:
        result = conn.call('RFC_GET_LOCAL_SERVERS')

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPISDORDER_GETDETAILEDLIST(conn, i_bapi_view = {}, i_memory_read = 'X', i_with_header_conditions = '', sales_documents = [], print_data = False):
    '''Sales Order detail - similar to transaction VA03

    Parameters
    ----------
    i_bapi_view : dict
    *   Bapi view for data restriction / filtering
    *   Structure: {'HEADER': 'X', 'ITEM': 'X', 'SDSCHEDULE': 'X', 'BUSINESS': 'X', 'PARTNER': 'X', 'ADDRESS': 'X', 'STATUS_H': 'X', 'STATUS_I': 'X',
                    'SDCOND': 'X', 'SDCOND_ADD': 'X', 'CONTRACT': 'X', 'TEXT': 'X', 'FLOW': 'X', 'BILLPLAN': 'X', 'CONFIGURE': 'X', 'CREDCARD': 'X', 'INCOMP_LOG': 'X'}

    i_memory_read: str
    *   Buffer access to SD tables
    *   Default value: 'X'

    i_with_header_conditions: str
    *   Default value: ''

    sales_documents : list
    *   VBELN sales document number
    *   Single or multiple sales documents
    *   Structure: [{'VBELN': ''}]

    Returns
    -------
    result : dict
    *   Message with transferred input parameters

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # i_bapi_view =                                 {'HEADER': 'X',
    #                                                'ITEM': 'X',
    #                                                'SDSCHEDULE': 'X',
    #                                                'BUSINESS': 'X',
    #                                                'PARTNER': 'X',
    #                                                'ADDRESS': 'X',
    #                                                'STATUS_H': 'X',
    #                                                'STATUS_I': 'X',
    #                                                'SDCOND': 'X',
    #                                                'SDCOND_ADD': 'X',
    #                                                'CONTRACT': 'X',
    #                                                'TEXT': 'X',
    #                                                'FLOW': 'X',
    #                                                'BILLPLAN': 'X',
    #                                                'CONFIGURE': 'X',
    #                                                'CREDCARD': 'X',
    #                                                'INCOMP_LOG': 'X'
    #                                               },
    # sales_documents =                             [{'VBELN': '0208796509'},
    #                                                {'VBELN': '0210801671'}
    #                                               ]

    try:
        result = conn.call('BAPISDORDER_GETDETAILEDLIST',
                           I_BAPI_VIEW = i_bapi_view,
                           I_MEMORY_READ = i_memory_read,
                           I_WITH_HEADER_CONDITIONS = i_with_header_conditions,
                           SALES_DOCUMENTS = sales_documents
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SALESORDER_GETLIST(conn, customer_number = '', sales_organization = '', material = '', document_date = '', document_date_to = '', transaction_group = '0', purchase_order_number = '',
                            material_evg = {}, material_long = '', sales_orders = [], extensionin = [], extensionex = [], print_data = False):
    '''Sales order: List of all Orders for Customer - similar to transaction VA05

    Parameters
    ----------
    customer_number : str
    *   Sold-to-party

    sales_organization : str
    *   Organizational unit responsible for the sales and distribution of certain products and services

    material: str
    *   Alphanumeric key that uniquely identifies the material

    document_date: str
    *   Entry date
    *   Format: 'YYYYMMDD'

    document_date_to: str
    *   Entry date up to and including
    *   Format: 'YYYYMMDD'

    transaction_group: str
    *   The transaction group controls which sales document types can be controlled with which system transactions during sales processing
    *   Default value: '0'
    *   Alternative values: 0 (Sales order),
                            1 (Customer inquiry),
                            2 (Quotation),
                            3 (Scheduling agreement),
                            4 (Contract),
                            5 (Item proposal),
                            6 (Delivery),
                            7 (Billing document)

    purchase_order_number: str
    *   Customer purchase order number

    material_evg: dict
    *   Material Number (40 Characters)

    material_long: str
    *   Material Number (40 Characters)

    sales_orders: list
    *   Structure: [{'SD_DOC': '208796509'}]

    extensionin: list
    *   Reference Structure for BAPI Parameters ExtensionIn/ExtensionOut

    extensionex: list
    *   Reference Structure for BAPI Parameters ExtensionIn/ExtensionOut

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # purchase_order_number =                       '0006030794.254654/01',

    try:
        result = conn.call('BAPI_SALESORDER_GETLIST',
                           CUSTOMER_NUMBER = customer_number,
                           SALES_ORGANIZATION = sales_organization,
                           MATERIAL = material,
                           DOCUMENT_DATE = document_date,
                           DOCUMENT_DATE_TO = document_date_to,
                           TRANSACTION_GROUP = transaction_group,
                           PURCHASE_ORDER_NUMBER = purchase_order_number,
                           MATERIAL_EVG = material_evg,
                           MATERIAL_LONG = material_long,
                           SALES_ORDERS = sales_orders,
                           EXTENSIONIN = extensionin,
                           EXTENSIONEX = extensionex
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SALESORDER_CHANGE(conn, salesdocument = '', order_header_in = {}, order_header_inx = {}, simulation = '', behave_when_error = '', int_number_assignment = '', logic_switch = {},
                           no_status_buf_init = '', order_item_in = [], order_item_inx = [], partners = [], partnerchanges = [], partneraddresses = [], order_cfgs_ref = [], order_cfgs_inst = [],
                           order_cfgs_part_of = [], order_cfgs_value = [], order_cfgs_blob = [], order_cfgs_vk = [], order_cfgs_refinst = [], schedule_lines = [], schedule_linesx = [],
                           order_text = [], order_keys = [], conditions_in = [], conditions_inx = [], extensionin = [], extensionex = [], print_data = False):

    '''Sales order: Change sales order (header / item level) - similar to transaction VA02

    Parameters
    ----------
    salesdocument: str
    *   Sales order number

    order_header_in: dict
    *   Sales order header

    order_header_inx: dict
    *   Sales order check list
    *   Controls processing functions with the value in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order,
        I   - Create a new sales order,
        U   - Change an existing sales order,
        D   - Delete an existing sales order

    *   If the UPDATEFLAG field has been activated, the system only copies those fields from the SALES_HEADER_IN parameter
        that have been activated with 'X'

    simulation: str
    *   Simulation mode

    behave_when_error: str
    *   Error handling
    *   ' ' - If an error occurs, processing stops and the sales order is not saved,
        P   - If an error occurs, the sales order can be saved
            - Problematic items are not processed but they are logged,
        R   - As for P but the order is not saved

    int_number_assignment: str
    *   Internal number assignment

    logic_switch: dict
    *   SD Checkbox for the Logic Switch

    no_status_buf_init: str
    *   No Refresh of Status Buffer

    order_item_in: list
    *   Order items

    order_item_inx: list
    *   Sales order items check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    schedule_lines: list
    *   Schedule lines in sales order

    schedule_linesx: list
    *   Schedule list check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    Returns
    -------
    result: dict
    *   List changed sales order fields with return message

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # Change Customer Material Number
    # -------------------------------
    # salesdocument =                               '0210436005',
    # order_header_in =                             {'SD_DOC_CAT': 'C'},        # Change flag
    # order_header_inx =                            {'UPDATEFLAG': 'U'},        # Update flag
    # order_item_in =                               [{'ITM_NUMBER': '000020',
    #                                                 'MATERIAL': '4052899936393',
    #                                                 'CUST_MAT22': 'TEST RFC 2',
    #                                                 'CUST_MAT35': 'TEST RFC 2',
    #                                               }],
    # order_item_inx =                              [{'ITM_NUMBER': '000020',
    #                                                 'UPDATEFLAG': 'U',
    #                                                 'CUST_MAT22': 'X',
    #                                                 'CUST_MAT35': 'X
    #                                               }],
    # schedule_lines =                              [{'ITM_NUMBER': '000020',
    #                                                 'SCHED_LINE': '0001',
    #                                               }],
    # schedule_linesx =                             [{'ITM_NUMBER': '000020',
    #                                                 'SCHED_LINE': '0001',
    #                                                 'UPDATEFLAG': 'U',
    #                                               }]
    #
    # Change Change Quantity
    # -------------------------------
    # salesdocument =                               '0210436005',
    # order_header_in =                             {'SD_DOC_CAT': 'C'},        # Change flag
    # order_header_inx =                            {'UPDATEFLAG': 'U'},        # Update flag
    # order_item_in =                               [{'ITM_NUMBER': '000020',
    #                                                 'MATERIAL': '4052899936393',
    #                                                 'TARGET_QTY': '11'
    #                                               }],
    # order_item_inx =                              [{'ITM_NUMBER': '000020',
    #                                                 'UPDATEFLAG': 'U',
    #                                                 'TARGET_QTY': 'X',
    #                                               }],
    # schedule_lines =                              [{'ITM_NUMBER': '000020',
    #                                                 'SCHED_LINE': '0001',
    #                                                 'REQ_QTY': '11'
    #                                               }],
    # schedule_linesx =                             [{'ITM_NUMBER': '000020',
    #                                                 'SCHED_LINE': '0001',
    #                                                 'UPDATEFLAG': 'U',
    #                                                 'REQ_QTY': 'X'
    #                                               }]
    #
    # Insert Line Item
    # -------------------------------
    # salesdocument =                               '0210436005',
    # order_header_in =                             {'SD_DOC_CAT': 'C'},        # Change flag
    # order_header_inx =                            {'UPDATEFLAG': 'U'},        # Update flag
    # order_item_in =                               [{'ITM_NUMBER': '000170',
    #                                                 'MATERIAL': '000004052899936386',  (18 digit material number)
    #                                                 'CUST_MAT22': 'Added RFC 123',
    #                                                 'CUST_MAT35': 'Added RFC 123',
    #                                                 'TARGET_QTY': '11'
    #                                               }],
    # order_item_inx =                              [{'ITM_NUMBER': '000170',
    #                                                 'UPDATEFLAG': 'I',
    #                                                 'MATERIAL': 'X',
    #                                                 'CUST_MAT22': 'X',
    #                                                 'CUST_MAT35': 'X',
    #                                                 'TARGET_QTY': 'X',
    #                                               }],
    # schedule_lines =                              [{'ITM_NUMBER': '000170',
    #                                                 'SCHED_LINE': '0001',
    #                                                 'REQ_QTY': '11'
    #                                               }],
    # schedule_linesx =                             [{'ITM_NUMBER': '000170',
    #                                                 'SCHED_LINE': '0001',
    #                                                 'UPDATEFLAG': 'I',
    #                                                 'REQ_QTY': 'X'
    #                                               }]

    try:
        result = conn.call('BAPI_SALESORDER_CHANGE',
                           SALESDOCUMENT = salesdocument,
                           ORDER_HEADER_IN = order_header_in,
                           ORDER_HEADER_INX = order_header_inx,
                           SIMULATION = simulation,
                           BEHAVE_WHEN_ERROR = behave_when_error,
                           INT_NUMBER_ASSIGNMENT = int_number_assignment,
                           LOGIC_SWITCH = logic_switch,
                           NO_STATUS_BUF_INIT = no_status_buf_init,
                           ORDER_ITEM_IN = order_item_in,
                           ORDER_ITEM_INX = order_item_inx,
                           PARTNERS = partners,
                           PARTNERCHANGES = partnerchanges,
                           PARTNERADDRESSES = partneraddresses,
                           ORDER_CFGS_REF = order_cfgs_ref,
                           ORDER_CFGS_INST = order_cfgs_inst,
                           ORDER_CFGS_PART_OF = order_cfgs_part_of,
                           ORDER_CFGS_VALUE = order_cfgs_value,
                           ORDER_CFGS_BLOB = order_cfgs_blob,
                           ORDER_CFGS_VK = order_cfgs_vk,
                           ORDER_CFGS_REFINST = order_cfgs_refinst,
                           SCHEDULE_LINES = schedule_lines,
                           SCHEDULE_LINESX = schedule_linesx,
                           ORDER_TEXT = order_text,
                           ORDER_KEYS = order_keys,
                           CONDITIONS_IN = conditions_in,
                           CONDITIONS_INX = conditions_inx,
                           EXTENSIONIN = extensionin,
                           EXTENSIONEX = extensionex,
                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SALESORDER_CREATEFROMDAT2(conn, salesdocumentin = '', order_header_in = {}, order_header_inx = {}, sender = {}, binary_relationshiptype = '', int_number_assignment = '', behave_when_error = '',
                                   logic_switch = {}, testrun = '', convert = '', order_items_in = [], order_items_inx = [], order_partners = [], order_schedules_in = [], order_schedules_inx = [],
                                   order_conditions_in = [], order_conditions_inx = [], order_cfgs_ref = [], order_cfgs_inst = [], order_cfgs_part_of = [], order_cfgs_value = [], order_cfgs_blob = [],
                                   order_cfgs_vk = [], order_cfgs_refinst = [], order_ccard = [], order_text = [], order_keys = [], extensionin = [], partneraddresses = [], extensionex = [], print_data = False):

    '''Sales order: Create sales order (header / item level) - similar to transaction VA01

    Parameters
    ----------
    salesdocumentin: str
    *   Sales order number

    order_header_in: dict
    *   Sales order header

    order_header_inx: dict
    *   Sales order check list
    *   Controls processing functions with the value in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order,
        I   - Create a new sales order,
        U   - Change an existing sales order,
        D   - Delete an existing sales order

    *   If the UPDATEFLAG field has been activated, the system only copies those fields from the SALES_HEADER_IN parameter
        that have been activated with 'X'

    sender: dict
    *   Logical system - sender

    binary_relationshiptype: str
    *   This parameter specifies the binary relationship type that is needed when writing object references
    *   The binary relationship type is defined in the VRBINRELATION view.
    *   Following type are available in SD:
        VORL Object references at header level2
        VORA Object references at item level
    *   Default value - SPACE

    int_number_assignment: str
    *   Internal item number assignment

    behave_when_error: str
    *   Error handling
    *   ' ' - If an error occurs, processing stops and the sales order is not saved,
        P   - If an error occurs, the sales order can be saved
            - Problematic items are not processed but they are logged,
        R   - As for P but the order is not saved

    int_number_assignment: str
    *   Internal number assignment

    logic_switch: dict
    *   SD Checkbox for the Logic Switch

    testrun: str
    *   This parameter is a test switch
    *   If you activate the switch, the system does not save the document
        Space - Document should be saved
        X     - Document should not be saved

    order_item_in: list
    *   Order items

    order_item_inx: list
    *   Sales order items check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_partners: list
    *   This parameter is used to enter partners such as sold-to party, ship-to party, both at header and item level
    *   The minimum requirement is that the sold-to party is entered at header level
    *   Additional partner functions can then be automatically determined.

    order_schedules_in: list
    *   Schedule lines in sales order

    order_schedules_inx: list
    *   Schedule list check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_conditions_in: list
    *   Condition data

    order_conditions_inx: list
    *   Conditions check list

    order_cfgs_ref: list
    *   Configuration: Reference data

    order_cfgs_inst: list
    *   Configuration: Instances

    order_cfgs_part_of: list
    *   Configuration: Part-of specifications

    order_cfgs_value: list
    *   Configuration: Characteristic calues

    order_cfgs_blob: list
    *   Configuration: BLOB internal data (SCE)

    order_cfgs_vk: list
    *   Configuration: Variant condition key

    order_cfgs_refinst: list
    *   Configuration: Reference item / Instance

    order_ccard: list
    *

    order_text: list
    *

    order_keys: list
    *   Output table of reference keys

    extensionin: list
    *   Customer enhancement for VBAK, VBAP, VBEP

    partneraddresses: list
    *   BAPI Reference Structure for Addresses (Org./Company)
    *   The structure corresponds to the structure of a CAM address (BAPIADDR1).

    extensionex: list
    *   Reference Structure for BAPI Parameters ExtensionIn / ExtensionOut

    Returns
    -------
    result: dict
    *   List changed sales order fields with return message

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------

    try:
        result = conn.call('BAPI_SALESORDER_CREATEFROMDAT2',
                           SALESDOCUMENTIN = salesdocumentin,
                           ORDER_HEADER_IN = order_header_in,
                           ORDER_HEADER_INX = order_header_inx,
                           SENDER = sender,
                           BINARY_RELATIONSHIPTYPE = binary_relationshiptype,
                           INT_NUMBER_ASSIGNMENT = int_number_assignment,
                           BEHAVE_WHEN_ERROR = behave_when_error,
                           LOGIC_SWITCH = logic_switch,
                           TESTRUN = testrun,
                           CONVERT = convert,
                           ORDER_ITEMS_IN = order_items_in,
                           ORDER_ITEMS_INX = order_items_inx,
                           ORDER_PARTNERS = order_partners,
                           ORDER_SCHEDULES_IN = order_schedules_in,
                           ORDER_SCHEDULES_INX = order_schedules_inx,
                           ORDER_CONDITIONS_IN = order_conditions_in,
                           ORDER_CONDITIONS_INX = order_conditions_inx,
                           ORDER_CFGS_REF = order_cfgs_ref,
                           ORDER_CFGS_INST = order_cfgs_inst,
                           ORDER_CFGS_PART_OF = order_cfgs_part_of,
                           ORDER_CFGS_VALUE = order_cfgs_value,
                           ORDER_CFGS_BLOB = order_cfgs_blob,
                           ORDER_CFGS_VK = order_cfgs_vk,
                           ORDER_CFGS_REFINST = order_cfgs_refinst,
                           ORDER_CCARD = order_ccard,
                           ORDER_TEXT = order_text,
                           ORDER_KEYS = order_keys,
                           EXTENSIONIN = extensionin,
                           PARTNERADDRESSES = partneraddresses,
                           EXTENSIONEX = extensionex
                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SALESORDER_CREATEFROMDAT1(conn, salesdocumentin = '', order_header_in = {}, order_header_inx = {}, sender = {}, binary_relationshiptype = '', int_number_assignment = '', behave_when_error = '',
                                   logic_switch = {}, testrun = '', convert = '', order_items_in = [], order_items_inx = [], order_partners = [], order_schedules_in = [], order_schedules_inx = [],
                                   order_conditions_in = [], order_conditions_inx = [], order_cfgs_ref = [], order_cfgs_inst = [], order_cfgs_part_of = [], order_cfgs_value = [], order_cfgs_blob = [],
                                   order_cfgs_vk = [], order_cfgs_refinst = [], order_ccard = [], order_text = [], order_keys = [], extensionin = [], partneraddresses = [], extensionex = [], print_data = False):

    '''Sales order: Create sales order (header / item level) - similar to transaction VA01

    Parameters
    ----------
    salesdocumentin: str
    *   Sales order number

    order_header_in: dict
    *   Sales order header

    order_header_inx: dict
    *   Sales order check list
    *   Controls processing functions with the value in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order,
        I   - Create a new sales order,
        U   - Change an existing sales order,
        D   - Delete an existing sales order

    *   If the UPDATEFLAG field has been activated, the system only copies those fields from the SALES_HEADER_IN parameter
        that have been activated with 'X'

    sender: dict
    *   Logical system - sender

    binary_relationshiptype: str
    *   This parameter specifies the binary relationship type that is needed when writing object references
    *   The binary relationship type is defined in the VRBINRELATION view.
    *   Following type are available in SD:
        VORL Object references at header level2
        VORA Object references at item level
    *   Default value - SPACE

    int_number_assignment: str
    *   Internal item number assignment

    behave_when_error: str
    *   Error handling
    *   ' ' - If an error occurs, processing stops and the sales order is not saved,
        P   - If an error occurs, the sales order can be saved
            - Problematic items are not processed but they are logged,
        R   - As for P but the order is not saved

    int_number_assignment: str
    *   Internal number assignment

    logic_switch: dict
    *   SD Checkbox for the Logic Switch

    testrun: str
    *   This parameter is a test switch
    *   If you activate the switch, the system does not save the document
        Space - Document should be saved
        X     - Document should not be saved

    order_item_in: list
    *   Order items

    order_item_inx: list
    *   Sales order items check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_partners: list
    *   This parameter is used to enter partners such as sold-to party, ship-to party, both at header and item level
    *   The minimum requirement is that the sold-to party is entered at header level
    *   Additional partner functions can then be automatically determined.

    order_schedules_in: list
    *   Schedule lines in sales order

    order_schedules_inx: list
    *   Schedule list check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_conditions_in: list
    *   Condition data

    order_conditions_inx: list
    *   Conditions check list

    order_cfgs_ref: list
    *   Configuration: Reference data

    order_cfgs_inst: list
    *   Configuration: Instances

    order_cfgs_part_of: list
    *   Configuration: Part-of specifications

    order_cfgs_value: list
    *   Configuration: Characteristic calues

    order_cfgs_blob: list
    *   Configuration: BLOB internal data (SCE)

    order_cfgs_vk: list
    *   Configuration: Variant condition key

    order_cfgs_refinst: list
    *   Configuration: Reference item / Instance

    order_ccard: list
    *

    order_text: list
    *

    order_keys: list
    *   Output table of reference keys

    extensionin: list
    *   Customer enhancement for VBAK, VBAP, VBEP

    partneraddresses: list
    *   BAPI Reference Structure for Addresses (Org./Company)
    *   The structure corresponds to the structure of a CAM address (BAPIADDR1).

    extensionex: list
    *   Reference Structure for BAPI Parameters ExtensionIn / ExtensionOut

    Returns
    -------
    result: dict
    *   List changed sales order fields with return message

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------

    try:
        result = conn.call('BAPI_SALESORDER_CREATEFROMDAT1',
                           ORDER_HEADER_IN = order_header_in,
                           WITHOUT_COMMIT = '',
                           CONVERT_PARVW_AUART = '',
                           ORDER_ITEMS_IN = order_items_in,
                           ORDER_PARTNERS = order_partners,
                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SD_SALESDOCUMENT_CREATE(conn, salesdocument = '', sales_header_in = {}, sales_header_inx = {}, sender = {}, binary_relationshiptype = '', int_number_assignment = '', behave_when_error = '',
                            logic_switch = {}, business_object = '', testrun = '', convert_parvw_auart = '', status_buffer_refresh = '', call_active = '', i_without_init = '', sales_items_in = [],
                            sales_items_inx = [], sales_partners = [], sales_schedules_in = [], sales_schedules_inx = [], sales_conditions_in = [], sales_conditions_inx = [], sales_cfgs_ref = [],
                            sales_cfgs_inst = [], sales_cfgs_part_of = [], sales_cfgs_value = [], sales_cfgs_blob = [], sales_cfgs_vk = [], sales_cfgs_refinst = [], sales_ccard = [], sales_text = [],
                            sales_keys = [], sales_contract_in = [], sales_contract_inx = [], extensionin = [], partneraddresses = [], sales_sched_conf_in = [], items_ex = [], schedule_ex = [], business_ex = [],
                            incomplete_log = [], extensionex = [], conditions_ex = [], partners_ex = [], textheaders_ex = [], textlines_ex = [], batch_charc = [], campaign_asgn = [], conditions_konv_ex = [],print_data = False):

    '''Sales order: Create sales order (header / item level) - similar to transaction VA01

    Parameters
    ----------
    salesdocumentin: str
    *   Sales order number

    order_header_in: dict
    *   Sales order header

    order_header_inx: dict
    *   Sales order check list
    *   Controls processing functions with the value in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order,
        I   - Create a new sales order,
        U   - Change an existing sales order,
        D   - Delete an existing sales order

    *   If the UPDATEFLAG field has been activated, the system only copies those fields from the SALES_HEADER_IN parameter
        that have been activated with 'X'

    sender: dict
    *   Logical system - sender

    binary_relationshiptype: str
    *   This parameter specifies the binary relationship type that is needed when writing object references
    *   The binary relationship type is defined in the VRBINRELATION view.
    *   Following type are available in SD:
        VORL Object references at header level2
        VORA Object references at item level
    *   Default value - SPACE

    int_number_assignment: str
    *   Internal item number assignment

    behave_when_error: str
    *   Error handling
    *   ' ' - If an error occurs, processing stops and the sales order is not saved,
        P   - If an error occurs, the sales order can be saved
            - Problematic items are not processed but they are logged,
        R   - As for P but the order is not saved

    int_number_assignment: str
    *   Internal number assignment

    logic_switch: dict
    *   SD Checkbox for the Logic Switch
    *   G   - Copy pricing elements unchanged and redetermine taxes

    testrun: str
    *   This parameter is a test switch
    *   If you activate the switch, the system does not save the document
        Space - Document should be saved
        X     - Document should not be saved

    order_item_in: list
    *   Order items

    order_item_inx: list
    *   Sales order items check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_partners: list
    *   This parameter is used to enter partners such as sold-to party, ship-to party, both at header and item level
    *   The minimum requirement is that the sold-to party is entered at header level
    *   Additional partner functions can then be automatically determined.

    order_schedules_in: list
    *   Schedule lines in sales order

    order_schedules_inx: list
    *   Schedule list check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_conditions_in: list
    *   Condition data

    order_conditions_inx: list
    *   Conditions check list

    order_cfgs_ref: list
    *   Configuration: Reference data

    order_cfgs_inst: list
    *   Configuration: Instances

    order_cfgs_part_of: list
    *   Configuration: Part-of specifications

    order_cfgs_value: list
    *   Configuration: Characteristic calues

    order_cfgs_blob: list
    *   Configuration: BLOB internal data (SCE)

    order_cfgs_vk: list
    *   Configuration: Variant condition key

    order_cfgs_refinst: list
    *   Configuration: Reference item / Instance

    order_ccard: list
    *

    order_text: list
    *

    order_keys: list
    *   Output table of reference keys

    extensionin: list
    *   Customer enhancement for VBAK, VBAP, VBEP

    partneraddresses: list
    *   BAPI Reference Structure for Addresses (Org./Company)
    *   The structure corresponds to the structure of a CAM address (BAPIADDR1).

    extensionex: list
    *   Reference Structure for BAPI Parameters ExtensionIn / ExtensionOut

    Returns
    -------
    result: dict
    *   List changed sales order fields with return message

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------

    try:
        result = conn.call('SD_SALESDOCUMENT_CREATE',
                           SALESDOCUMENT = salesdocument,
                           SALES_HEADER_IN = sales_header_in,
                           SALES_HEADER_INX = sales_header_inx,
                           SENDER = sender,
                           BINARY_RELATIONSHIPTYPE = binary_relationshiptype,
                           INT_NUMBER_ASSIGNMENT = int_number_assignment,
                           BEHAVE_WHEN_ERROR = behave_when_error,
                           LOGIC_SWITCH = logic_switch,
                           BUSINESS_OBJECT = business_object,
                           TESTRUN = testrun,
                           CONVERT_PARVW_AUART = convert_parvw_auart,
                           STATUS_BUFFER_REFRESH = status_buffer_refresh,
                           CALL_ACTIVE = call_active,
                           I_WITHOUT_INIT = i_without_init,
                           SALES_ITEMS_IN = sales_items_in,
                           SALES_ITEMS_INX = sales_items_inx,
                           SALES_PARTNERS = sales_partners,
                           SALES_SCHEDULES_IN = sales_schedules_in,
                           SALES_SCHEDULES_INX = sales_schedules_inx,
                           SALES_CONDITIONS_IN = sales_conditions_in,
                           SALES_CONDITIONS_INX = sales_conditions_inx,
                           SALES_CFGS_REF = sales_cfgs_ref,
                           SALES_CFGS_INST = sales_cfgs_inst,
                           SALES_CFGS_PART_OF = sales_cfgs_part_of,
                           SALES_CFGS_VALUE = sales_cfgs_value,
                           SALES_CFGS_BLOB = sales_cfgs_blob,
                           SALES_CFGS_VK = sales_cfgs_vk,
                           SALES_CFGS_REFINST = sales_cfgs_refinst,
                           SALES_CCARD = sales_ccard,
                           SALES_TEXT = sales_text,
                           SALES_KEYS = sales_keys,
                           SALES_CONTRACT_IN = sales_contract_in,
                           SALES_CONTRACT_INX = sales_contract_inx,
                           EXTENSIONIN = extensionin,
                           PARTNERADDRESSES = partneraddresses,
                           SALES_SCHED_CONF_IN = sales_sched_conf_in,
                           ITEMS_EX = items_ex,
                           SCHEDULE_EX = schedule_ex,
                           BUSINESS_EX = business_ex,
                           INCOMPLETE_LOG = incomplete_log,
                           EXTENSIONEX = extensionex,
                           CONDITIONS_EX = conditions_ex,
                           PARTNERS_EX = partners_ex,
                           TEXTHEADERS_EX = textheaders_ex,
                           TEXTLINES_EX = textlines_ex,
                           BATCH_CHARC = batch_charc,
                           CAMPAIGN_ASGN = campaign_asgn,
                           CONDITIONS_KONV_EX = conditions_konv_ex,

                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SD_SALESDOCUMENT_CHANGE(conn, salesdocument = '', order_header_in = {}, order_header_inx = {}, simulation = '', int_number_assignment = '', behave_when_error = '', business_object = '', convert_parvw_auart = '', call_from_bapi = '', logic_switch = {},
                            i_crm_lock_mode = '', no_status_buf_init = '', call_active = '', i_without_init = '', item_in = [], item_inx = [], schedule_in = [], schedule_inx = [], partners = [], partnerchanges = [], partneraddresses = [], sales_cfgs_ref = [],
                            sales_cfgs_inst = [], sales_cfgs_part_of = [], sales_cfgs_value = [], sales_cfgs_blob = [], sales_cfgs_vk = [], sales_cfgs_refinst = [], sales_ccard = [], sales_text = [], sales_keys = [], conditions_in = [], conditions_inx = [],
                            sales_contract_in = [], sales_contract_inx = [], extensionin = [], items_ex = [], schedule_ex = [], business_ex = [], incomplete_log = [], extensionex = [], conditions_ex = [], sales_sched_conf_in = [], del_schedule_ex = [],
                            del_schedule_in = [], del_schedule_inx = [], corr_cumqty_in = [], corr_cumqty_inx = [], corr_cumqty_ex = [], partners_ex = [], textheaders_ex = [], textlines_ex = [], batch_charc = [], campaign_asgn = [], conditions_konv_ex = [], print_data = False):
    '''Sales order: Change sales document (header / item level) - similar to transaction VA02

    Parameters
    ----------
    salesdocumentin: str
    *   Sales order number

    order_header_in: dict
    *   Sales order header

    order_header_inx: dict
    *   Sales order check list
    *   Controls processing functions with the value in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order,
        I   - Create a new sales order,
        U   - Change an existing sales order,
        D   - Delete an existing sales order

    *   If the UPDATEFLAG field has been activated, the system only copies those fields from the SALES_HEADER_IN parameter
        that have been activated with 'X'

    sender: dict
    *   Logical system - sender

    binary_relationshiptype: str
    *   This parameter specifies the binary relationship type that is needed when writing object references
    *   The binary relationship type is defined in the VRBINRELATION view.
    *   Following type are available in SD:
        VORL Object references at header level2
        VORA Object references at item level
    *   Default value - SPACE

    int_number_assignment: str
    *   Internal item number assignment

    behave_when_error: str
    *   Error handling
    *   ' ' - If an error occurs, processing stops and the sales order is not saved,
        P   - If an error occurs, the sales order can be saved
            - Problematic items are not processed but they are logged,
        R   - As for P but the order is not saved

    int_number_assignment: str
    *   Internal number assignment

    logic_switch: dict
    *   SD Checkbox for the Logic Switch
    *   G   - Copy pricing elements unchanged and redetermine taxes

    testrun: str
    *   This parameter is a test switch
    *   If you activate the switch, the system does not save the document
        Space - Document should be saved
        X     - Document should not be saved

    order_item_in: list
    *   Order items

    order_item_inx: list
    *   Sales order items check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_partners: list
    *   This parameter is used to enter partners such as sold-to party, ship-to party, both at header and item level
    *   The minimum requirement is that the sold-to party is entered at header level
    *   Additional partner functions can then be automatically determined.

    order_schedules_in: list
    *   Schedule lines in sales order

    order_schedules_inx: list
    *   Schedule list check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_conditions_in: list
    *   Condition data

    order_conditions_inx: list
    *   Conditions check list

    order_cfgs_ref: list
    *   Configuration: Reference data

    order_cfgs_inst: list
    *   Configuration: Instances

    order_cfgs_part_of: list
    *   Configuration: Part-of specifications

    order_cfgs_value: list
    *   Configuration: Characteristic calues

    order_cfgs_blob: list
    *   Configuration: BLOB internal data (SCE)

    order_cfgs_vk: list
    *   Configuration: Variant condition key

    order_cfgs_refinst: list
    *   Configuration: Reference item / Instance

    order_ccard: list
    *

    order_text: list
    *

    order_keys: list
    *   Output table of reference keys

    extensionin: list
    *   Customer enhancement for VBAK, VBAP, VBEP

    partneraddresses: list
    *   BAPI Reference Structure for Addresses (Org./Company)
    *   The structure corresponds to the structure of a CAM address (BAPIADDR1).

    extensionex: list
    *   Reference Structure for BAPI Parameters ExtensionIn / ExtensionOut

    Returns
    -------
    result: dict
    *   List changed sales order fields with return message

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------

    try:
        result = conn.call('SD_SALESDOCUMENT_CHANGE',
                           SALESDOCUMENT = salesdocument,
                           ORDER_HEADER_IN = order_header_in,
                           ORDER_HEADER_INX = order_header_inx,
                           SIMULATION = simulation,
                           INT_NUMBER_ASSIGNMENT = int_number_assignment,
                           BEHAVE_WHEN_ERROR = behave_when_error,
                           BUSINESS_OBJECT = business_object,
                           CONVERT_PARVW_AUART = convert_parvw_auart,
                           CALL_FROM_BAPI = call_from_bapi,
                           LOGIC_SWITCH = logic_switch,
                           I_CRM_LOCK_MODE = i_crm_lock_mode,
                           NO_STATUS_BUF_INIT = no_status_buf_init,
                           CALL_ACTIVE = call_active,
                           I_WITHOUT_INIT = i_without_init,
                           ITEM_IN = item_in,
                           ITEM_INX = item_inx,
                           SCHEDULE_IN = schedule_in,
                           SCHEDULE_INX = schedule_inx,
                           PARTNERS = partners,
                           PARTNERCHANGES = partnerchanges,
                           PARTNERADDRESSES = partneraddresses,
                           SALES_CFGS_REF = sales_cfgs_ref,
                           SALES_CFGS_INST = sales_cfgs_inst,
                           SALES_CFGS_PART_OF = sales_cfgs_part_of,
                           SALES_CFGS_VALUE = sales_cfgs_value,
                           SALES_CFGS_BLOB = sales_cfgs_blob,
                           SALES_CFGS_VK = sales_cfgs_vk,
                           SALES_CFGS_REFINST = sales_cfgs_refinst,
                           SALES_CCARD = sales_ccard,
                           SALES_TEXT = sales_text,
                           SALES_KEYS = sales_keys,
                           CONDITIONS_IN = conditions_in,
                           CONDITIONS_INX = conditions_inx,
                           SALES_CONTRACT_IN = sales_contract_in,
                           SALES_CONTRACT_INX = sales_contract_inx,
                           EXTENSIONIN = extensionin,
                           ITEMS_EX = items_ex,
                           SCHEDULE_EX = schedule_ex,
                           BUSINESS_EX = business_ex,
                           INCOMPLETE_LOG = incomplete_log,
                           EXTENSIONEX = extensionex,
                           CONDITIONS_EX = conditions_ex,
                           SALES_SCHED_CONF_IN = sales_sched_conf_in,
                           DEL_SCHEDULE_EX = del_schedule_ex,
                           DEL_SCHEDULE_IN = del_schedule_in,
                           DEL_SCHEDULE_INX = del_schedule_inx,
                           CORR_CUMQTY_IN = corr_cumqty_in,
                           CORR_CUMQTY_INX = corr_cumqty_inx,
                           CORR_CUMQTY_EX = corr_cumqty_ex,
                           PARTNERS_EX = partners_ex,
                           TEXTHEADERS_EX = textheaders_ex,
                           TEXTLINES_EX = textlines_ex,
                           BATCH_CHARC = batch_charc,
                           CAMPAIGN_ASGN = campaign_asgn,
                           CONDITIONS_KONV_EX = conditions_konv_ex,




                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SALESDOCUMENT_CHANGE(conn, salesdocument = '', order_header_in = {}, order_header_inx = {}, simulation = '', int_number_assignment = '', behave_when_error = '', business_object = '', convert_parvw_auart = '', call_from_bapi = '', logic_switch = {},
                            i_crm_lock_mode = '', no_status_buf_init = '', call_active = '', i_without_init = '', item_in = [], item_inx = [], schedule_in = [], schedule_inx = [], partners = [], partnerchanges = [], partneraddresses = [], sales_cfgs_ref = [],
                            sales_cfgs_inst = [], sales_cfgs_part_of = [], sales_cfgs_value = [], sales_cfgs_blob = [], sales_cfgs_vk = [], sales_cfgs_refinst = [], sales_ccard = [], sales_text = [], sales_keys = [], conditions_in = [], conditions_inx = [],
                            sales_contract_in = [], sales_contract_inx = [], extensionin = [], items_ex = [], schedule_ex = [], business_ex = [], incomplete_log = [], extensionex = [], conditions_ex = [], sales_sched_conf_in = [], del_schedule_ex = [],
                            del_schedule_in = [], del_schedule_inx = [], corr_cumqty_in = [], corr_cumqty_inx = [], corr_cumqty_ex = [], partners_ex = [], textheaders_ex = [], textlines_ex = [], batch_charc = [], campaign_asgn = [], conditions_konv_ex = [], print_data = False):
    '''Sales order: Change sales document (header / item level) - similar to transaction VA02

    Parameters
    ----------
    salesdocumentin: str
    *   Sales order number

    order_header_in: dict
    *   Sales order header

    order_header_inx: dict
    *   Sales order check list
    *   Controls processing functions with the value in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order,
        I   - Create a new sales order,
        U   - Change an existing sales order,
        D   - Delete an existing sales order

    *   If the UPDATEFLAG field has been activated, the system only copies those fields from the SALES_HEADER_IN parameter
        that have been activated with 'X'

    sender: dict
    *   Logical system - sender

    binary_relationshiptype: str
    *   This parameter specifies the binary relationship type that is needed when writing object references
    *   The binary relationship type is defined in the VRBINRELATION view.
    *   Following type are available in SD:
        VORL Object references at header level2
        VORA Object references at item level
    *   Default value - SPACE

    int_number_assignment: str
    *   Internal item number assignment

    behave_when_error: str
    *   Error handling
    *   ' ' - If an error occurs, processing stops and the sales order is not saved,
        P   - If an error occurs, the sales order can be saved
            - Problematic items are not processed but they are logged,
        R   - As for P but the order is not saved

    int_number_assignment: str
    *   Internal number assignment

    logic_switch: dict
    *   SD Checkbox for the Logic Switch
    *   G   - Copy pricing elements unchanged and redetermine taxes

    testrun: str
    *   This parameter is a test switch
    *   If you activate the switch, the system does not save the document
        Space - Document should be saved
        X     - Document should not be saved

    order_item_in: list
    *   Order items

    order_item_inx: list
    *   Sales order items check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_partners: list
    *   This parameter is used to enter partners such as sold-to party, ship-to party, both at header and item level
    *   The minimum requirement is that the sold-to party is entered at header level
    *   Additional partner functions can then be automatically determined.

    order_schedules_in: list
    *   Schedule lines in sales order

    order_schedules_inx: list
    *   Schedule list check list
    *   Processing in the UPDATEFLAG field (change indicator)
        ' ' - Create a new sales order item,
        I   - Create a new sales order item,
        U   - Change an existing sales order item,
        D   - Delete an existing sales order item

    *   If the UPDATEFLAG field is active, the system only copies data parameter fields that have an 'X' in the checkbox

    order_conditions_in: list
    *   Condition data

    order_conditions_inx: list
    *   Conditions check list

    order_cfgs_ref: list
    *   Configuration: Reference data

    order_cfgs_inst: list
    *   Configuration: Instances

    order_cfgs_part_of: list
    *   Configuration: Part-of specifications

    order_cfgs_value: list
    *   Configuration: Characteristic calues

    order_cfgs_blob: list
    *   Configuration: BLOB internal data (SCE)

    order_cfgs_vk: list
    *   Configuration: Variant condition key

    order_cfgs_refinst: list
    *   Configuration: Reference item / Instance

    order_ccard: list
    *

    order_text: list
    *

    order_keys: list
    *   Output table of reference keys

    extensionin: list
    *   Customer enhancement for VBAK, VBAP, VBEP

    partneraddresses: list
    *   BAPI Reference Structure for Addresses (Org./Company)
    *   The structure corresponds to the structure of a CAM address (BAPIADDR1).

    extensionex: list
    *   Reference Structure for BAPI Parameters ExtensionIn / ExtensionOut

    Returns
    -------
    result: dict
    *   List changed sales order fields with return message

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------

    try:
        result = conn.call('BAPI_SALESDOCUMENT_CHANGE',
                           SALESDOCUMENT = salesdocument,
                           ORDER_HEADER_IN = order_header_in,
                           ORDER_HEADER_INX = order_header_inx,
                           SIMULATION = simulation,
                        #    INT_NUMBER_ASSIGNMENT = int_number_assignment,
                        #    BEHAVE_WHEN_ERROR = behave_when_error,
                        #    BUSINESS_OBJECT = business_object,
                        #    CONVERT_PARVW_AUART = convert_parvw_auart,
                        #    CALL_FROM_BAPI = call_from_bapi,
                        #    LOGIC_SWITCH = logic_switch,
                        #    I_CRM_LOCK_MODE = i_crm_lock_mode,
                        #    NO_STATUS_BUF_INIT = no_status_buf_init,
                        #    CALL_ACTIVE = call_active,
                        #    I_WITHOUT_INIT = i_without_init,
                           ITEM_IN = item_in,
                           ITEM_INX = item_inx,
                           SCHEDULE_IN = schedule_in,
                           SCHEDULE_INX = schedule_inx,
                        #    PARTNERS = partners,
                        #    PARTNERCHANGES = partnerchanges,
                        #    PARTNERADDRESSES = partneraddresses,
                           SALES_CFGS_REF = sales_cfgs_ref,
                           SALES_CFGS_INST = sales_cfgs_inst,
                           SALES_CFGS_PART_OF = sales_cfgs_part_of,
                           SALES_CFGS_VALUE = sales_cfgs_value,
                           SALES_CFGS_BLOB = sales_cfgs_blob,
                        #    SALES_CFGS_VK = sales_cfgs_vk,
                        #    SALES_CFGS_REFINST = sales_cfgs_refinst,
                        #    SALES_CCARD = sales_ccard,
                        #    SALES_TEXT = sales_text,
                        #    SALES_KEYS = sales_keys,
                        #    CONDITIONS_IN = conditions_in,
                        #    CONDITIONS_INX = conditions_inx,
                        #    SALES_CONTRACT_IN = sales_contract_in,
                        #    SALES_CONTRACT_INX = sales_contract_inx,
                        #    EXTENSIONIN = extensionin,
                        #    ITEMS_EX = items_ex,
                        #    SCHEDULE_EX = schedule_ex,
                        #    BUSINESS_EX = business_ex,
                        #    INCOMPLETE_LOG = incomplete_log,
                        #    EXTENSIONEX = extensionex,
                        #    CONDITIONS_EX = conditions_ex,
                        #    SALES_SCHED_CONF_IN = sales_sched_conf_in,
                        #    DEL_SCHEDULE_EX = del_schedule_ex,
                        #    DEL_SCHEDULE_IN = del_schedule_in,
                        #    DEL_SCHEDULE_INX = del_schedule_inx,
                        #    CORR_CUMQTY_IN = corr_cumqty_in,
                        #    CORR_CUMQTY_INX = corr_cumqty_inx,
                        #    CORR_CUMQTY_EX = corr_cumqty_ex,
                        #    PARTNERS_EX = partners_ex,
                        #    TEXTHEADERS_EX = textheaders_ex,
                        #    TEXTLINES_EX = textlines_ex,
                        #    BATCH_CHARC = batch_charc,
                        #    CAMPAIGN_ASGN = campaign_asgn,
                        #    CONDITIONS_KONV_EX = conditions_konv_ex,




                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_GETDETAIL(conn, number = '', print_data = False):
    '''QM Notification: Read Detail Data - similar to transaction QM02

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_QUALNOT_GETDETAIL',
                           NUMBER = number,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_MODIFY_DATA(conn, number = '', notifheader = {}, notifheader_x = {}, notifheader_export = {}, notifitem = [], notifitem_x = [], notifcaus = [], notifcaus_x = [], notifactv = [], notifactv_x = [],
                             notiftask = [], notiftask_x = [], notifpartnr = [], notifpartnr_x = [], notfulltxt = [], print_data = False):
    '''QM Notification: Change Data - similar to transaction QM02

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_QUALNOT_MODIFY_DATA',
                           NUMBER = number,
                           NOTIFHEADER = notifheader,
                           NOTIFHEADER_X = notifheader_x,
                           NOTIFHEADER_EXPORT = notifheader_export,
                           NOTIFITEM = notifitem,
                           NOTIFITEM_X = notifitem_x,
                           NOTIFCAUS = notifcaus,
                           NOTIFCAUS_X = notifcaus_x,
                           NOTIFACTV = notifactv,
                           NOTIFACTV_X = notifactv_x,
                           NOTIFTASK = notiftask,
                           NOTIFTASK_X = notiftask_x,
                           NOTIFPARTNR = notifpartnr,
                           NOTIFPARTNR_X = notifpartnr_x,
                           NOTFULLTXT = notfulltxt,
                          )

        message_save = BAPI_QUALNOT_SAVE(conn, number = number)
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        result.update({'NOTIFHEADER': message_save['NOTIFHEADER'], 'SAVE_RETURN': message_save['RETURN']})

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_ADD_DATA(conn, number = '', notifheader = {}, sender = {}, notfulltxt = [], notitem = [], notifcaus = [], notifactv = [], notiftask = [], notifpartnr = [], key_relationships = [], print_data = False):
    '''QM Notification: Add Data - similar to transaction QM02

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',


    try:
        result = conn.call('BAPI_QUALNOT_ADD_DATA',
                           NUMBER = number,
                           NOTIFHEADER = notifheader,
                           SENDER = sender,
                           NOTFULLTXT = notfulltxt,
                           NOTITEM = notitem,
                           NOTIFCAUS = notifcaus,
                           NOTIFACTV = notifactv,
                           NOTIFTASK = notiftask,
                           NOTIFPARTNR = notifpartnr,
                           KEY_RELATIONSHIPS = key_relationships,
                          )

        message = BAPI_QUALNOT_SAVE(conn, number = number)
        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

        if len(result["RETURN"]) != 0 and result["RETURN"][0]["TYPE"] == "E":
            err_msg = result["RETURN"][0]["MESSAGE"]

            if "locked by G.ROBOT_RFC" in err_msg:
                raise NotificationLockedError(err_msg)

            if "does not exist" in err_msg:
                raise NotificationDoesNotExistError(err_msg)

            raise RuntimeError(err_msg)


    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_CREATE(conn, external_number = '', notif_type = '', notifheader = {}, task_determination = {}, sender = {}, notitem = [], notifcaus = [], notifactv = [], notiftask = [], notifpartnr = [],
                        longtexts = [], key_relationships = [], print_data = False):
    '''QM Notification: Create QM - similar to transaction QM01

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',
    # notifheader =                                 {
    #                                                 'REFOBJECTTYPE': ''
    #                                                 'REFOBJECTKEY': '',
    #                                                 'REFRELTYPE': '',
    #                                                 'SHORT_TEXT': '',          # Description
    #                                                 'PRIORITY': '',            # Priority
    #                                                 'NOTIFTIME': '',
    #                                                 'NOTIF_DATE': '',
    #                                                 'REPORTEDBY': '',
    #                                                 'STARTDATE': '',
    #                                                 'DESSTTIME': '',
    #                                                 'ENDDATE': '',
    #                                                 'DESENDTM': '',
    #                                                 'CATALOGUE': '',
    #                                                 'CODE_GROUP': '',          # Claim type
    #                                                 'CODE': '',                # Claim type
    #                                                 'MATERIAL_PLANT': '',
    #                                                 'MATERIAL': '',
    #                                                 'REV_LEV': '',
    #                                                 'ADDITIONAL_DEVICE_DATA': '',
    #                                                 'BATCH': '1234',
    #                                                 'STOR_LOC_BATCH': '',
    #                                                 'VENDRBATCH': '',
    #                                                 'MATERIAL_CUSTOMER': '',
    #                                                 'VEND_MAT': '',
    #                                                 'MPN': '',
    #                                                 'SERIALNO': '',
    #                                                 'EQUIPMENT': '',
    #                                                 'SALES_ORD': '',
    #                                                 'S_ORD_ITEM': '',
    #                                                 'PURCH_NO_C': '',
    #                                                 'PURCH_DATE': '',
    #                                                 'DELIV_NUMB': '',          # Delivery number
    #                                                 'DELIV_ITEM': '',
    #                                                 'DIVISION': '',
    #                                                 'SALESORG': '',
    #                                                 'DISTR_CHAN': '',
    #                                                 'CUST_NO': '',             # Sold-to
    #                                                 'PO_NUMBER': '',
    #                                                 'PO_ITEM': '',
    #                                                 'DOC_YEAR': '',
    #                                                 'MAT_DOC': '',
    #                                                 'MAT_DOC_ITEM': '',
    #                                                 'PURCH_ORG': '',
    #                                                 'PUR_GROUP': '',
    #                                                 'VEND_NO': '',
    #                                                 'MANUFACTURER': '',
    #                                                 'VERSION': '',
    #                                                 'MATERIAL_PRODUCTION': '',
    #                                                 'PLANT': '',
    #                                                 'PROD_ORDER': '',
    #                                                 'PROD_ORDER_OP_PLAN': '',
    #                                                 'INSPOPER_INT': '',
    #                                                 'OBJECT_TYPE_CIM_RESOURCE': '',
    #                                                 'WORK_CTR': '',
    #                                                 'WORK_CTR_PLANT': '',
    #                                                 'QUANT_COMPLAINT': '',
    #                                                 'MATERIAL_EXTERNAL': '',
    #                                                 'MATERIAL_GUID': '',
    #                                                 'MATERIAL_VERSION': '',
    #                                                 'MATERIAL_PRODUCTION_EXTERNAL': '',
    #                                                 'MATERIAL_PRODUCTION_GUID': '',
    #                                                 'MATERIAL_PRODUCTION_VERSION': '',
    #                                                 'MPN_EXTERNAL': '',
    #                                                 'MPN_GUID': '',
    #                                                 'MPN_VERSION': '',
    #                                                 'QTY_UNIT': '',
    #                                                 'ISOCODE_UNIT': '',
    #                                                 'MATERIAL_LONG': '',
    #                                                 'MPN_LONG': '',
    #                                                 'MATERIAL_PRODUCTION_LONG': '',
    #                                                 },










    try:
        result = conn.call('BAPI_QUALNOT_CREATE',
                           EXTERNAL_NUMBER = external_number,
                           NOTIF_TYPE = notif_type,
                           NOTIFHEADER = notifheader,
                           TASK_DETERMINATION = task_determination,
                           SENDER = sender,
                           NOTITEM = notitem,
                           NOTIFCAUS = notifcaus,
                           NOTIFACTV = notifactv,
                           NOTIFTASK = notiftask,
                           NOTIFPARTNR = notifpartnr,
                           LONGTEXTS = longtexts,
                           KEY_RELATIONSHIPS = key_relationships
                          )

        message_save = BAPI_QUALNOT_SAVE(conn, number = result['NOTIFHEADER_EXPORT']['NOTIF_NO'])
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        result.update({'NOTIFHEADER': message_save['NOTIFHEADER'], 'SAVE_RETURN': message_save['RETURN']})

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_SAVE(conn, number = '', print_data = False):
    '''Save QM Notification

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_QUALNOT_SAVE',
                           NUMBER = number,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_DEL_DATA(conn, number = '', print_data = False):
    '''QM Notification: Delete Data

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_QUALNOT_DEL_DATA',
                           NUMBER = number,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SERVNOT_ADD_DATA(conn, number = '', i_bapi = '', notfulltxt = [], notitem = [], notifcaus = [], notifactv = [], notiftask = [], notifpartnr = [], key_relationships = [], print_data = False):
    '''SM Notification: Add Data - similar to transaction QM02

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',


    try:
        result = conn.call('BAPI_SERVNOT_ADD_DATA',
                           NUMBER = number,
                           I_BAPI = i_bapi,
                           NOTFULLTXT = notfulltxt,
                           NOTITEM = notitem,
                           NOTIFCAUS = notifcaus,
                           NOTIFACTV = notifactv,
                           NOTIFTASK = notiftask,
                           NOTIFPARTNR = notifpartnr,
                           KEY_RELATIONSHIPS = key_relationships,
                          )

        message = BAPI_SERVNOT_SAVE(conn, number = number)
        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SERVNOT_SAVE(conn, number = '', print_data = False):
    '''Save QM Notification

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_SERVNOT_SAVE',
                           NUMBER = number,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SERVNOT_CLOSE(conn, number = '', syststat = {}, testrun = '', print_data = False):
    '''Complete QM Notification

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_SERVNOT_CLOSE',
                           NUMBER = number,
                           SYSTSTAT = syststat,
                           TESTRUN = testrun,
                          )

        message_save = BAPI_SERVNOT_SAVE(conn, number = number)
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        result.update({'NOTIFHEADER': message_save['NOTIFHEADER'], 'SAVE_RETURN': message_save['RETURN']})

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SERVNOT_GET_DETAIL(conn, number = '', print_data = False):
    '''QM Notification: Read Detail Data - similar to transaction QM02

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_SERVNOT_GET_DETAIL',
                           NUMBER = number,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result


def HRIQ_GUID_CREATE_RFC(conn, print_data = False):
    '''Create GUID 32

    Parameters
    ----------

    Returns
    -------
    result: dict
    *   GUID 32

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------

    try:
        result = conn.call('HRIQ_GUID_CREATE_RFC')

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_DISPUTE_CREATE(conn, case_guid_create = '', case_type = '', testrun = '', update_task = 'X', amounts_delta = {}, note_properties = {}, attributes = [], notes = [], filecontent = [], objects = [], fileclassification = [], print_data = False):
    '''FSCM-DM: Create Dispute Case

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_DISPUTE_CREATE',
                           CASE_GUID_CREATE = case_guid_create,
                           CASE_TYPE = case_type,
                           TESTRUN = testrun,
                           UPDATE_TASK = update_task,
                           AMOUNTS_DELTA = amounts_delta,
                           NOTE_PROPERTIES = note_properties,
                           ATTRIBUTES = attributes,
                           NOTES = notes,
                           FILECONTENT = filecontent,
                           OBJECTS = objects,
                           FILECLASSIFICATION = fileclassification,
                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_COMPLSTAT(conn, number = '', syststat = {}, testrun = '', print_data = False):
    '''Complete QM Notification

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    try:
        result = conn.call(
            'BAPI_QUALNOT_COMPLSTAT',
            NUMBER = number,
            SYSTSTAT = syststat,
            TESTRUN = testrun,
        )
        
        message_save = BAPI_QUALNOT_SAVE(conn, number)
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        result.update({
            'NOTIFHEADER': message_save['NOTIFHEADER'],
            'SAVE_RETURN': message_save['RETURN']
        })

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_RELSTAT(conn, number = '', langu = 'EN', languiso = '', testrun = '', print_data = False):
    '''Put QM Notification in Process

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call(
            'BAPI_QUALNOT_RELSTAT',
            NUMBER = number,
            LANGU = langu,
            LANGUISO = languiso,
            TESTRUN =  testrun,
        )

        if len(result['RETURN']) != 0 and result['RETURN'][0]["TYPE"] == "E":
            
            if result['RETURN'][0]["MESSAGE_V3"] == "Notification in process":
                raise NotificationInProcessWarning(result['RETURN'][0]["MESSAGE"])

            if result['SYSTEMSTATUS'] == "NOCO NOTI DLFL":
                raise NotificationDeletedError("Cannot modify a notification marked with a deletion flag!")
    
            raise RuntimeError(result['RETURN'][0]["MESSAGE"])

        message_save = BAPI_QUALNOT_SAVE(conn, number = number)
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        result.update({'NOTIFHEADER': message_save['NOTIFHEADER'], 'SAVE_RETURN': message_save['RETURN']})

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise
    
    return result

def BAPI_SERVNOT_PUTINPROGRESS(conn, number = '', langu = 'EN', languiso = '', testrun = '', print_data = False):
    '''Put SM Notification in Process

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_SERVNOT_PUTINPROGRESS',
                           NUMBER = number,
                           LANGU = langu,
                           LANGUISO = languiso,
                           TESTRUN =  testrun,
                          )

        message_save = BAPI_SERVNOT_SAVE(conn, number = number)
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        result.update({'NOTIFHEADER': message_save['NOTIFHEADER'], 'SAVE_RETURN': message_save['RETURN']})

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_QUALNOT_CHANGETSKSTAT(conn, number = '', task_key = '0000', task_code = '', carried_out_by = '', carried_out_date = '', carried_out_time = '', langu = 'EN', languiso = '', testrun = '', print_data = False):
    '''QM Notification: Change Task

    Parameters
    ----------
    number: str
    *   Number of the notification that is to be completed

    task_code: str
    *   '01' = The system status "Task Completed" is assigned to the task.
    *   '02' = The system status "Task Released" is assigned to the task
    *   '03' = The system status "Task Successful" is assigned to the task.

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_QUALNOT_CHANGETSKSTAT',
                           NUMBER = number,
                           TASK_KEY = task_key,
                           TASK_CODE = task_code,
                           CARRIED_OUT_BY = carried_out_by,
                           CARRIED_OUT_DATE = carried_out_date,
                           CARRIED_OUT_TIME = carried_out_time,
                           LANGU = langu,
                           LANGUISO = languiso,
                           TESTRUN = testrun,
                          )

        message_save = BAPI_QUALNOT_SAVE(conn, number = number)
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        result.update({'NOTIFHEADER': message_save['NOTIFHEADER'], 'SAVE_RETURN': message_save['RETURN']})

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SERVNOT_COMPLETE_TASK(conn, number = '', task_key = '0000', carried_out_by = '', carried_out_date = '', carried_out_time = '', langu = 'EN', languiso = '', testrun = '', print_data = False):
    '''QM Notification: Change Task

    Parameters
    ----------
    number: str
    *   Number of the notification that is to be completed

    task_code: str
    *   '01' = The system status "Task Completed" is assigned to the task.
    *   '02' = The system status "Task Released" is assigned to the task
    *   '03' = The system status "Task Successful" is assigned to the task.

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_SERVNOT_COMPLETE_TASK',
                           NUMBER = number,
                           TASK_KEY = task_key,
                           CARRIED_OUT_BY = carried_out_by,
                           CARRIED_OUT_DATE = carried_out_date,
                           CARRIED_OUT_TIME = carried_out_time,
                           LANGU = langu,
                           LANGUISO = languiso,
                           TESTRUN = testrun,
                          )

        message_save = BAPI_SERVNOT_SAVE(conn, number = number)
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        result.update({'NOTIFHEADER': message_save['NOTIFHEADER'], 'SAVE_RETURN': message_save['RETURN']})

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def IQS4_GET_NOTIFICATION(conn, i_qmnum = '', print_data = False):
    '''PM/QM/SM Notification - read data

    Parameters
    ----------
    i_qmnum: str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('IQS4_GET_NOTIFICATION',
                           I_QMNUM = i_qmnum
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def IQS4_SAVE_NOTIFICATION(conn, i_qmnum = '', i_commit = 'X', i_wait = '', i_refresh_complete = 'X', print_data = False):
    '''PM/QM/SM Notification - read data

    Parameters
    ----------
    i_qmnum: str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('IQS4_SAVE_NOTIFICATION',
                           I_QMNUM = i_qmnum,
                           I_COMMIT = i_commit,
                           I_WAIT = i_wait,
                           I_REFRESH_COMPLETE = i_refresh_complete,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def IQS4_CREATE_NOTIFICATION(conn, i_qmnum = '', i_aufnr = '', i_riqs5 = {}, i_task_det = '', i_conv = '', i_bin_relationship = '', i_sender = {}, i_post = 'X', i_commit = '', i_wait = '', i_refresh_complete = 'X',
                             i_check_parnr_comp = 'X', i_rfc_call = '', i_rbnr = '', i_notif_copy = '', i_dms_copy = '', i_inlines_t = [], i_viqmfe_t = [], i_viqmur_t = [], i_viqmsm_t = [], i_viqmma_t = [],
                             i_ihpa_t = [], e_keys = [], e_bin_relation_tab = [], print_data = False):
    '''PM/QM/SM Notification - create

    Parameters
    ----------
    i_qmnum: str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',
    #
    # Tables
    # ------------------------------------------------------------------------------------------------------------------
    # VIQMEL =                                      Notification header

    try:
        result = conn.call('IQS4_CREATE_NOTIFICATION',
                           I_QMNUM = i_qmnum,
                           I_AUFNR = i_aufnr,
                           I_RIQS5 = i_riqs5,
                           I_TASK_DET = i_task_det,
                           I_CONV = i_conv,
                           I_BIN_RELATIONSHIP = i_bin_relationship,
                           I_SENDER = i_sender,
                           I_POST = i_post,
                           I_COMMIT = i_commit,
                           I_WAIT = i_wait,
                           I_REFRESH_COMPLETE = i_refresh_complete,
                           I_CHECK_PARNR_COMP = i_check_parnr_comp,
                           I_RFC_CALL = i_rfc_call,
                           I_RBNR = i_rbnr,
                           I_NOTIF_COPY = i_notif_copy,
                           I_DMS_COPY = i_dms_copy,
                           I_INLINES_T = i_inlines_t,
                           I_VIQMFE_T = i_viqmfe_t,
                           I_VIQMUR_T = i_viqmur_t,
                           I_VIQMSM_T = i_viqmsm_t,
                           I_VIQMMA_T = i_viqmma_t,
                           I_IHPA_T = i_ihpa_t,
                           E_KEYS = e_keys,
                           E_BIN_RELATION_TAB = e_bin_relation_tab,
                          )

        message_save = IQS4_SAVE_NOTIFICATION(conn, i_qmnum = i_qmnum)
        message_commit = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def IQS4_ADD_DATA_NOTIFICATION(conn, i_qmnum = '', i_conv = '', i_post = 'X', i_commit = '', i_wait = '', i_refresh_complete = 'X', i_check_parnr_comp = 'X', i_bapi = '', i_no_buffer_refresh_on_error = '',
                               i_inlines_t = [], i_viqmfe_t = [], i_viqmur_t = [], i_viqmsm_t = [], i_viqmma_t = [], i_ihpa_t = [], e_keys = [], print_data = False):
    '''PM/QM/SM Notification - add data

    Parameters
    ----------
    i_qmnum: str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('IQS4_ADD_DATA_NOTIFICATION',
                           I_QMNUM = i_qmnum,
                           I_CONV = i_conv,
                           I_POST = i_post,
                           I_COMMIT = i_commit,
                           I_WAIT = i_wait,
                           I_REFRESH_COMPLETE = i_refresh_complete,
                           I_CHECK_PARNR_COMP = i_check_parnr_comp,
                           I_BAPI = i_bapi,
                           I_NO_BUFFER_REFRESH_ON_ERROR = i_no_buffer_refresh_on_error,
                           I_INLINES_T = i_inlines_t,
                           I_VIQMFE_T = i_viqmfe_t,
                           I_VIQMUR_T = i_viqmur_t,
                           I_VIQMSM_T = i_viqmsm_t,
                           I_VIQMMA_T = i_viqmma_t,
                           I_IHPA_T = i_ihpa_t,
                           E_KEYS = e_keys,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def IQS4_CHANGE_STATUS_TASK(conn,  i_qmnum = '', i_manum = '', i_vrgng = '', i_check_only = '', i_spras = 'EN', i_erlnam = '', i_erldat = '', i_erlzeit = '', i_post = 'X', i_commit = '', i_wait = '',
                            i_refresh_complete = 'X', p_head_nochange = '', print_data = False):
    '''PM/QM/SM Notification - change task status

    Parameters
    ----------
    i_qmnum: str
    *   Number of the notification that is to be completed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('IQS4_CHANGE_STATUS_TASK',
                           I_QMNUM = i_qmnum,
                           I_MANUM = i_manum,
                           I_VRGNG = i_vrgng,
                           I_CHECK_ONLY = i_check_only,
                           I_SPRAS = i_spras,
                           I_ERLNAM = i_erlnam,
                           I_ERLDAT = i_erldat,
                           I_ERLZEIT = i_erlzeit,
                           I_POST = i_post,
                           I_COMMIT = i_commit,
                           I_WAIT = i_wait,
                           I_REFRESH_COMPLETE = i_refresh_complete,
                           P_HEAD_NOCHANGE = p_head_nochange,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def IQS4_MODIFY_NOTIFICATION(conn, notif: int, payload: dict) -> dict:
    """
    Note: The function is a prototype only.
    Modifies params of an existing service notification

    Params:
    -------
    conn:
        A SAP RFC connection object.

    notif:
        Service notification number.

    payload:
    --------
        Notification arameters to update.

    Returns:
    --------
    Query result stored as dict.
    """

    result = conn.call(
        'IQS4_MODIFY_NOTIFICATION',
        I_QMNUM = notif,
        I_RIQS5_NEW = payload
    )

    return result

def SAP_WAPI_GET_WI_ALL(conn,  language = 'EN', with_deadlines = '', print_data = False):
    '''Workflow interfaces - Build worklist for users

    Parameters
    ----------
    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    with_deadlines: str
    *   Apply deadline filter

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('SAP_WAPI_GET_WI_ALL',
                           LANGUAGE = language,
                           WITH_DEADLINES = with_deadlines,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SAP_WAPI_GET_WORKITEM_DETAIL(conn,  workitem_id = '', user = '', language = 'EN', translate_wi_text = '', print_data = False):
    '''Workflow interfaces - Read details about the work item

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    user: str
    *   SAP System, User Logon Name

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    translate_wi_text: str
    *   Translate work item text

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # user =                                        'MARTIN.GLEZL',
    # language =                                    'EN',
    # translate_wi_text =                           ''SWWWIHEAD

    # Tables:
    # -----------------------------------------------------------------------------------------
    # SWWWIHEAD =                                   Header information of work item

    try:
        result = conn.call('SAP_WAPI_GET_WORKITEM_DETAIL',
                           WORKITEM_ID = workitem_id,
                           USER = user,
                           LANGUAGE = language,
                           TRANSLATE_WI_TEXT = translate_wi_text,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SAP_WAPI_FORWARD_WORKITEM(conn,  workitem_id = '', user_id = '', language = 'EN', do_commit = 'X', current_user = '', check_inbox_restriction = '', print_data = False):
    '''Workflow interfaces - Forward Work Item

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    user_id: str
    *   SAP System, User Logon Name

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    do_commit: str
    *   Execute Commit

    current_user: str
    *   Forwarding User

    check_inbox_restriction: str

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # user_id =                                     'MARTIN.GLEZL',
    # language =                                    'EN',
    # do_commit =                                   'X',
    # current_user =                                'MARTIN.GLEZL',
    # check_inbox_restriction =                     ''

    try:
        result = conn.call('SAP_WAPI_FORWARD_WORKITEM',
                           WORKITEM_ID = workitem_id,
                           USER_ID = user_id,
                           LANGUAGE = language,
                           DO_COMMIT = do_commit,
                           CURRENT_USER = current_user,
                           CHECK_INBOX_RESTRICTION = check_inbox_restriction,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SAP_WAPI_EXECUTE_WORKITEM(conn,  workitem_id = '', language = 'EN', print_data = False):
    '''Workflow Interfaces: Execute Work Item

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # language =                                    'EN',

    try:
        result = conn.call('SAP_WAPI_EXECUTE_WORKITEM',
                           WORKITEM_ID = workitem_id,
                           LANGUAGE = language,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SAP_WAPI_SET_WORKITEM_COMPLETD(conn,  workitem_id = '', actual_agent = '', language = 'EN', check_inbox_restriction = 'X', print_data = False):
    '''Workflow Interfaces: Set Work Item to Completed

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    actual_agent: str
    *   SAP System, User Logon Name

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    do_commit: str
    *   Execute Commit

    current_user: str
    *   Forwarding User

    check_inbox_restriction: str

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # actual_agent =                                'MARTIN.GLEZL',
    # language =                                    'EN',
    # check_inbox_restriction =                     ''

    try:
        result = conn.call('SAP_WAPI_SET_WORKITEM_COMPLETD',
                           WORKITEM_ID = workitem_id,
                           ACTUAL_AGENT = actual_agent,
                           LANGUAGE = language,
                           CHECK_INBOX_RESTRICTION = check_inbox_restriction,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SAP_WAPI_SUBFLOW_COMPLETE(conn,  workitem_id = '', actual_agent = '', language = 'EN', set_obsolet = '', do_commit = 'X', do_callback_in_background = 'X', print_data = False):
    '''Workflow Interfaces: Set Work Item to Completed

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    actual_agent: str
    *   SAP System, User Logon Name

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    do_commit: str
    *   Execute Commit

    current_user: str
    *   Forwarding User

    check_inbox_restriction: str

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # actual_agent =                                'MARTIN.GLEZL',
    # language =                                    'EN',
    # check_inbox_restriction =                     ''

    try:
        result = conn.call('SAP_WAPI_SUBFLOW_COMPLETE',
                           WORKITEM_ID = workitem_id,
                           ACTUAL_AGENT = actual_agent,
                           LANGUAGE = language,
                           SET_OBSOLET = set_obsolet,
                           DO_COMMIT = do_commit,
                           DO_CALLBACK_IN_BACKGROUND = do_callback_in_background,
                        #    IFS_XML_CONTAINER = ifs_xml_container,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SAP_WAPI_WORKITEM_COMPLETE(conn,  workitem_id = '', actual_agent = '', language = 'EN', set_obsolet = '', do_commit = 'X', do_callback_in_background = 'X', check_inbox_restriction = '', print_data = False):
    '''Workflow Interfaces: Set Work Item to Completed

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    actual_agent: str
    *   SAP System, User Logon Name

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    do_commit: str
    *   Execute Commit

    current_user: str
    *   Forwarding User

    check_inbox_restriction: str

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # actual_agent =                                'MARTIN.GLEZL',
    # language =                                    'EN',
    # check_inbox_restriction =                     ''

    try:
        result = conn.call('SAP_WAPI_WORKITEM_COMPLETE',
                           WORKITEM_ID = workitem_id,
                           ACTUAL_AGENT = actual_agent,
                           LANGUAGE = language,
                           SET_OBSOLET = set_obsolet,
                           DO_COMMIT = do_commit,
                           DO_CALLBACK_IN_BACKGROUND = do_callback_in_background,
                        #    IFS_XML_CONTAINER = ifs_xml_container,
                           CHECK_INBOX_RESTRICTION = check_inbox_restriction,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SWW_WI_FORWARD(conn,  current_user = '', wi_id = '', do_commit = 'X', preconditions_checked = '', im_funcname = '', admin_mode_no_x_check = '', new_agents = [], print_data = False):
    '''Workflow Interfaces: Forward Work Item (All Types)

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    actual_agent: str
    *   SAP System, User Logon Name

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    do_commit: str
    *   Execute Commit

    current_user: str
    *   Forwarding User

    check_inbox_restriction: str

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # actual_agent =                                'MARTIN.GLEZL',
    # language =                                    'EN',
    # check_inbox_restriction =                     ''

    try:
        result = conn.call('SWW_WI_FORWARD',
                           CURRENT_USER = current_user,
                           WI_ID = wi_id,
                           DO_COMMIT = do_commit,
                           PRECONDITIONS_CHECKED = preconditions_checked,
                           IM_FUNCNAME = im_funcname,
                           ADMIN_MODE_NO_X_CHECK = admin_mode_no_x_check,
                           NEW_AGENTS = new_agents,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SWW_WI_REJECT(conn,  wi_id = '', user = '', do_commit = 'X', debug_flag = '', no_callback_on_completion = '', preconditions_checked = '', im_funcname = '', print_data = False):
    '''Workflow Interfaces: Forward Work Item (All Types)

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    actual_agent: str
    *   SAP System, User Logon Name

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    do_commit: str
    *   Execute Commit

    current_user: str
    *   Forwarding User

    check_inbox_restriction: str

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # actual_agent =                                'MARTIN.GLEZL',
    # language =                                    'EN',
    # check_inbox_restriction =                     ''

    try:
        result = conn.call('SWW_WI_REJECT',
                           WI_ID = wi_id,
                           USER = user,
                           DO_COMMIT = do_commit,
                           DEBUG_FLAG = debug_flag,
                           NO_CALLBACK_ON_COMPLETION = no_callback_on_completion,
                           PRECONDITIONS_CHECKED = preconditions_checked,
                           IM_FUNCNAME = im_funcname,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def SAP_WAPI_DECISION_COMPLETE(conn,  workitem_id = '', language = 'EN', user = '', decision_key = '0000', do_commit = 'X', decision_note = {}, check_inbox_restriction = '', print_data = False):
    '''Workflow Interfaces: Set Work Item to Completed

    Parameters
    ----------
    workitem_id: str
    *   Work Item ID

    actual_agent: str
    *   SAP System, User Logon Name

    language: str
    *   SAP R/3 System, Current Language
    *   Default value - 'EN'

    do_commit: str
    *   Execute Commit

    current_user: str
    *   Forwarding User

    check_inbox_restriction: str

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # workitem_id =                                 '000049009709',
    # actual_agent =                                'MARTIN.GLEZL',
    # language =                                    'EN',
    # check_inbox_restriction =                     ''

    try:
        result = conn.call('SAP_WAPI_DECISION_COMPLETE',
                           WORKITEM_ID = workitem_id,
                           LANGUAGE = language,
                           USER = user,
                           DECISION_KEY = decision_key,
                           DO_COMMIT = do_commit,
                           DECISION_NOTE = decision_note,
                           CHECK_INBOX_RESTRICTION = check_inbox_restriction,
                          )

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SALESDOCUMENT_COPY(conn, salesdocument = '', documenttype = '', testrun = '', print_data = False):
    '''Copy Sales Document to a Subsequent Document

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_SALESDOCUMENT_COPY',
                            SALESDOCUMENT = salesdocument,
                            DOCUMENTTYPE = documenttype,
                            TESTRUN = testrun,
                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def BAPI_SALESDOCU_CREATEFROMDATA(conn, order_header_in = {}, business_object = '', without_commit = '', convert_parvw_auart = '', order_items_in = [], order_partners = [],
                                  order_items_out = [], order_cfgs_ref = [], order_cfgs_inst = [], order_cfgs_part_of = [], order_cfgs_value = [], order_cfgs_blob = [], order_ccard = [],
                                  order_schedule_ex = [], print_data = False):
    '''Create Sales Document

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # number =                                      '1001279631',

    try:
        result = conn.call('BAPI_SALESDOCU_CREATEFROMDATA',
                            ORDER_HEADER_IN = order_header_in,
                            BUSINESS_OBJECT = business_object,
                            WITHOUT_COMMIT = without_commit,
                            CONVERT_PARVW_AUART = convert_parvw_auart,
                            ORDER_ITEMS_IN = order_items_in,
                            ORDER_PARTNERS = order_partners,
                            ORDER_ITEMS_OUT = order_items_out,
                            ORDER_CFGS_REF = order_cfgs_ref,
                            ORDER_CFGS_INST = order_cfgs_inst,
                            ORDER_CFGS_PART_OF = order_cfgs_part_of,
                            ORDER_CFGS_VALUE = order_cfgs_value,
                            ORDER_CFGS_BLOB = order_cfgs_blob,
                            ORDER_CCARD = order_ccard,
                            ORDER_SCHEDULE_EX = order_schedule_ex,
                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def Z_FI25_MONITOR_ORDERS(conn, credat_s = '', credat_e = '', upddat_s = '', upddat_e = '', status = [], idoctp = [], mestyp = [], kunnr = [], docnum_i = [], edidc = [], print_data = False):
    '''Monitor orderes idoc -/WSW/SPEEDI_TR018

    Parameters
    ----------
    number : str
    *   Number of the notification that is to be processed

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # DDSIGN =                                      Values      Description             https://www.sapdatasheet.org/abap/doma/ddsign.html
    #                                               I  	 	    Range limit included
    #                                               E  	 	    Range limit excluded
    #
    # DDOPTION =                                    Values      Description             https://www.sapdatasheet.org/abap/doma/ddoption.html
    #                                               EQ  	 	Equals
    #                                               BT  	 	Between ... and ...
    #                                               CP  	 	Contains the template
    #                                               LE  	 	Less than or equal to
    #                                               GE  	 	Greater than or equal to
    #                                               NE  	 	Not equal to
    #                                               NB  	 	Not between ... and ...
    #                                               NP  	 	Does not contain the template
    #                                               GT  	 	Greater than
    #                                               LT  	 	Less than

    try:
        result = conn.call('Z_FI25_MONITOR_ORDERS',
                           CREDAT_S = credat_s,
                           CREDAT_E = credat_e,
                           UPDDAT_S = upddat_s,
                           UPDDAT_E = upddat_e,
                           STATUS = status,
                           IDOCTP = idoctp,
                           MESTYP = mestyp,
                           KUNNR = kunnr,
                           DOCNUM_I = docnum_i,
                           EDIDC = edidc
                          )

        # message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def Z_FI25_PROCESS_ORDERS(conn, mode = 'E', docnum_i = [], status = [], print_data = False):
    '''Process IDoc

    Parameters
    ----------
    mode : str
    *   Batch data communication mode
    *   Default value - 'E'
    *   Possible entries:
        - "A"	Processing with screens displayed
        - "E"	Screens displayed only if an error occurs
        - "N"	Processing without screens displayed. If a breakpoint is reached in one of the called transactions, processing is terminated with sy-subrc equal to 1001.
                The field sy-msgty contains "S", sy-msgid contains "00", sy-msgno contains "344", sy-msgv1 contains "SAPMSSY3", and sy-msgv2 contains "0131".

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # DDSIGN =                                      Values      Description             https://www.sapdatasheet.org/abap/doma/ddsign.html
    #                                               I  	 	    Range limit included
    #                                               E  	 	    Range limit excluded
    #
    # DDOPTION =                                    Values      Description             https://www.sapdatasheet.org/abap/doma/ddoption.html
    #                                               EQ  	 	Equals
    #                                               BT  	 	Between ... and ...
    #                                               CP  	 	Contains the template
    #                                               LE  	 	Less than or equal to
    #                                               GE  	 	Greater than or equal to
    #                                               NE  	 	Not equal to
    #                                               NB  	 	Not between ... and ...
    #                                               NP  	 	Does not contain the template
    #                                               GT  	 	Greater than
    #                                               LT  	 	Less than

    try:
        result = conn.call('Z_FI25_PROCESS_ORDERS',
                           MODE = mode,
                           DOCNUM_I = docnum_i,
                           STATUS = status,
                          )

        # message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def ZQM25_CLAIM_DISPUTE_POST(conn, is_viqmel = {}, print_data = False):
    '''Create FSCM Dispute case and sync notification

    Parameters
    ----------
    is_viqmel : list
    *   Generated Table for View

    Returns
    -------
    result: dict
    *   List of orders for customer

    EXAMPLE params in function
    ----------
    '''

    # Sample params
    # ------------------------------------------------------------------------------------------------------------------
    # DDSIGN =                                      Values      Description             https://www.sapdatasheet.org/abap/doma/ddsign.html
    #                                               I  	 	    Range limit included
    #                                               E  	 	    Range limit excluded
    #
    # DDOPTION =                                    Values      Description             https://www.sapdatasheet.org/abap/doma/ddoption.html
    #                                               EQ  	 	Equals
    #                                               BT  	 	Between ... and ...
    #                                               CP  	 	Contains the template
    #                                               LE  	 	Less than or equal to
    #                                               GE  	 	Greater than or equal to
    #                                               NE  	 	Not equal to
    #                                               NB  	 	Not between ... and ...
    #                                               NP  	 	Does not contain the template
    #                                               GT  	 	Greater than
    #                                               LT  	 	Less than

    try:
        result = conn.call('ZQM25_CLAIM_DISPUTE_POST',
                           IS_VIQMEL = is_viqmel,
                          )

        message = BAPI_TRANSACTION_COMMIT(conn)

        if print_data == True:
            pp.pprint(result)

    except CommunicationError:
        print("Could not connect to server.")
        raise
    except LogonError:
        print("Could not log in. Wrong credentials?")
        raise
    except (ABAPApplicationError, ABAPRuntimeError):
        print("An error occurred.")
        raise

    return result

def disconnect():
    """
    Closes an active connection
    to SAP backend system.
    """

    global connection

    if connection is None:
        g_log.warning("Attempt to close a non-existent SAP connection ignored.")
        return

    connection.close()
    connection = None

def connect(**kwargs):
    """
    Opens connection to SAP backend system.

    kwargs:
    -------
    user: `str`
        User name.

    passwd: `str`
        User password.

    ashost: `str`
        Name of the SAP backend host server.

    sysnr: `str`
        A 2-digit number that represents the SAP system to connect.

    client: `str`
        A 3-digit number that represents the sender client ('Mandant').

    debugging: `bool`
        If True, debug messages will be logged into a 'dev_rfc.log' file.

    Returns:
    -------
    An instance of class `pyrfc.Connection` that \n
    represents the connection to a SAP backend system.
    """

    global connection

    if connection is not None:
        g_log.warning("An active conection already exists! No new connection will be created.")
        return connection

    connection = Connection(
        user = kwargs["user"],
        passwd = kwargs["passwd"],
        ashost = kwargs["ashost"],
        sysnr = kwargs["sysnr"],
        client = kwargs["client"]
    )

    if not ("debugging" in kwargs and kwargs["debugging"]):
        try:
            os.remove(join(sys.path[0], "dev_rfc.log"))
        except Exception as exc:
            print(str(exc))

def format_number(num: Union[str,int], n_digits: int = 10) -> str:
    """
    Convert a number to RFC-mandated string format.

    Params:
    -------
    num: number to format.
    n_digits: Digit count of the formatted number.

    Result:
    -------
    Formatted number.

    If the digit count in the input number is lower than \n
    the required number of digits, then the number will \n
    be zero-padded to that length.
    """

    if not isinstance(num, (str, int)):
        raise ValueError(f"Number of type 'str' or 'int' expected, but got '{type(num)}'!")

    return str(num).zfill(n_digits)

def format_number2(
        num: Union[str,float],
        decimal_sep: str = ',',
        decimals: int = 2) -> str:
    """
    Formats a number into SAP-accepted string.

    Params:
    -------
    num: Number to format.
    decimal_sep: Decimap separator used in the resulting number.
    decimals: Decimal places to round the resulting number.

    Returns:
    --------
    Formatted string number.
    """

    if not isinstance(num, (str,float)):
        raise TypeError(f"Expected number type was 'str' or 'float', but got '{type(num)}'!")

    minus_sign = "-"
    coeff = 1
    decimals = max(decimals, 0) # bottom cap the number of decimal places
    val = str(num).strip()

    if minus_sign in val:
        val = val.strip(minus_sign)
        coeff = -1

    tokens = re.split(r"\D", val)
    n_decimals = len(tokens[-1]) if len(tokens) != 1 else 0

    val = re.sub(r"\D", "", num)
    val = (int(val) / 10 ** n_decimals) * coeff

    val = str(val).replace(".", decimal_sep)
    n_decimals = val[::-1].find(decimal_sep)
    val = val + "0" * (decimals - n_decimals)

    return val

def get_current_time(fmt: str = None) -> Union[datetime,str]:
    """
    Return current time.

    Params:
    ------
    fmt:
        String that controls th resulting time format. \n
        If None is used (default value), then an unformatted \n
        time vlue will be returned.

    Returns:
    --------
    Cuurrent time.
    """

    curr_time = datetime.now()

    if fmt is not None:
        return curr_time.strftime(fmt)

    return curr_time

def get_case_type(comp_code: str) -> str:
    """Returns case type value for a given company code."""

    case_type = int(comp_code) % 1000
    case_type = str(case_type).zfill(4)

    return case_type

def get_sales_organization(comp_code: str) -> str:
    """Returns sales organization code for a given company code."""
    return get_case_type(comp_code)

def get_help(func_name: str) -> str:
    """Returns a detailed documentation for a function."""
    return RFC_FUNCTION_DESCRIPTION(connection, func_name)

# Notes
# ----------------------------------------------------------
# BAPI_DISPUTE_CREATE
# BAPI_DISPUTE_FILECONTENT
# CV120_GET_MIME_TYPE
# 'MIMETYPE': 'application/pdf'  text/plain

# case_id= 10225682 000D3A206F061EDB97D27915EC88803B
# EXT_REF 123
# C:\Users\mglezl\OneDrive - LEDVANCE GmbH\Desktop\TEST_UPLOAD_RFC.pdf
# INSERT ls_mod_value INTO TABLE t_mod_value
# handle_data_change
# COMMIT or ROLLBACK. To COMMIT call BAPI BAPI_TRANSACTION_COMMIT
# table UDMCASEATTR00 SCMG_T_CASE_ATTR SOOD SOFM
# GUI_UPLOAD
# # options = [{ 'TEXT': "FCURR = 'USD'"}]

# SRGBTBREL > SO_DOCUMENT_READ_API1
# J_3RF_TP_FL_CREATE_ATTACHMENT
# CVAPI_DOC_CHECKIN > CVAPI01
# GOS_API_GET_ATTA_LIST
# SO_DOCUMENT_READ_API1



# Tables:
# -----------------------------------------------------------------------------------------
# SCMG_T_CASE_ATTR =                        Case Attributes
# SRGBTBREL =                               SAP Relationships in GOS Environment Table and data
# TSOTD =                                   Valid Object Types




# Articles:
# -----------------------------------------------------------------------------------------
# https://answers.sap.com/questions/8654868/rfcs-to-create-gos-attachment.html
# https://blogs.sap.com/2020/05/22/upload-download-attachments-in-dispute-managementfscm/
# https://www.inwerken.de/gos-anhange-auslesen-anlegen/
# https://answers.sap.com/questions/10071949/need-a-function-module-or-bapi-to-attach-files-to-.html
# https://answers.sap.com/questions/1286352/archivelink-rfc.html
# http://mysaplib.com/00001048/4f9939e1446d11d189700000e8322d00/content.htm
# https://blogs.sap.com/2020/05/22/upload-download-attachments-in-dispute-managementfscm/
# https://blogs.sap.com/2014/09/11/downloading-a-sq01-or-sqvi-query-with-net-connector/
# https://answers.sap.com/questions/2472675/in-fm-wht-is-selname.html
# https://blogs.sap.com/2013/12/02/how-to-make-sqvi-personalized-queries-available-to-other-users/
# https://answers.sap.com/questions/6340460/how-to-insert-items-using-bapisalesorderchange.html
# https://answers.sap.com/questions/3204971/bapisalesordercreatefromdat2-sample.html
# https://sap4tech.net/sap-qm-bapi-main/




# Table STXH / STXL Basic Data Text
# Text Object = MATERIAL
# Text Name = Material Number (101226950100)
# Text ID = GRUN (basic data text)
# Text ID = BEST (PO text)


# BAPI_MATERIAL_SAVEDATA
# BAPI_MATERIAL_GET_ALL
# RSAQ_REMOTE_QUERY_CALL
# RSAQ_REMOTE_QUERY_FIELDLIST
# RPY_PROGRAM_READ
# RFC_CALL_TRANSACTION_USING
# ABAP4_CALL_TRANSACTION
# Idoc Monitoring - WE02


# BAPISDORDER_GETDETAILEDLIST
# BAPI_SALESORDER_CHANGE
# 210436005


# Assigned report: AQ50 SYSTQV000316 VBAK_VBAP=====
# VBELN S I EQ 1100000




# we02 t-code is used get the related data regarding the Idoc number or idoc type or message type..

# if you know the idoc number..

# all the data which is showing in the We02 is stored in EDID4--data records..

# EDIDC-control data

# EDIDS-status data.

# write the select query using idoc number and read the dat..

# int_seg --is nothing but EDID4 data

# i_listedidc --is nothing but EDIDC control data






# SPEEDI FMs / BAPIs
# /WSW/SPEEDI_BAPI_SALESORDER_CR    SPEEDI: Create salesorder (all)
# /WSWBASE/SPEEDI_CALL_REP034       SPEEDI: Submit report /WSW/SPEEDI_REP034 (supporting RFC)
# /WSWBASE/SPEEDI_INBOUND_SINGLE    SPEEDI: Function module to IDoc inbound single


# QM01 / QM02 BAPIs
# BAPI_QUALNOT_CREATE
# BAPI_QUALNOT_ADD_DATA
# BAPI_QUALNOT_MODIFY_DATA


# QM 1001279631


# Find dispute case table: SCMG_T_CASE_ATTR, UDMCASEATTR00
# table: ORBRELTYP for BINRELTYP

# BUS2030 Customer inquiry
# BUS2031 Customer quotation
# BUS2032 Sales order
# BUS2034 Contracts
# BUS2094 Credit memo request
# BUS2096 Debit memo request
# BUS2102 Returns
# BUS2103 Subsequent delivery free of charge




# BAPI_DRMCREDITMEMOREQ_CREATE
# BAPI_DRMDEBITMEMOREQ_CREATE
# BAPI_SALESDOCU_CREATEFROMDATA BUS2094 https://www.stechies.com/bapis-sales-distribution/
# https://answers.sap.com/questions/177600/programmatically-update-prices-of-item-conditions-.html
# https://answers.sap.com/questions/3179193/repricing-in-sales-order-using-bapi.html


# Job scheduling
# BAPI_XBP_JOB_OPEN
# BAPI_XBP_JOB_ADD_ABAP_STEP
# BAPI_XBP_JOB_ADD_EXT_STEP
# BAPI_XBP_JOB_CLOSE
# BAPI_XBP_JOB_START_IMMEDIATELY
# BAPI_XBP_JOB_START_ASAP
# https://answers.sap.com/questions/3785646/bapi-for-scheduling-a-background-job.html
# https://www.guru99.com/background-job-processing.html
