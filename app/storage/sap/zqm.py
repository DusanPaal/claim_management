# pylint: disable = C0301, R0912, R0913, R0914

"""Mediates operations performed in SAP ZQM25_T001 Transaction."""

from . import rfc, Account

_codes = {

    "quality": {
        "category": "006",
        "reason": "6Q",
    },

    "bonus": {
        "category": "013",
        "reason": "XXX",
    },

    "promo": {
        "category": "008",
        "reason": "8Y3",
    },

}

def create_notification(
    acc: Account, reference_no: str,
    desc: str, category_name: str,
    amount: float, company_code: str) -> tuple:
    """
    Creates a new YD-type service notification.

    Params:
    -------
    acc:
        Customer account number.

    reference_no:
        Text entered into the field 'Reference no.' located in a QM transaction.

    desc:
        Text entered into the field 'Description' located in a QM transaction.

    category_name:
        Name of the document category:
        - quality
        - promo
        - bonus

    amount:
        Total customer-disputed amount of a debit note.

    company_code:
        A 4-digit code thet represents the central organizational unit of external \n
        accounting  under which the customer is registered within the SAP System:
        - '1001': Germany
        - '1072': Austria
        - '0074': Switzerland

    Returns:
    --------
    A tuple of the notification ID (`int`), case ID (`int`) and case GUID (`str`).
    """

    if not isinstance(acc, Account):
        raise TypeError(f"Account value of type 'Account' expected, but got '{type(acc)}'!")

    if not isinstance(reference_no, str):
        raise TypeError(f"Reference no. value of type 'str' expected, but got '{type(reference_no)}'!")

    if reference_no == "":
        raise ValueError("Reference no. value is an empty string!")

    if not isinstance(desc, str):
        raise TypeError(f"Description value of type 'str' expected, but got {type(desc)}!")

    if desc == "":
        raise ValueError("Description value is an empty string!")

    if category_name not in _codes:
        raise ValueError(f"Unrecognized category name: '{category_name}'!")

    if not isinstance(amount, float):
        raise TypeError(f"Amount value of type 'float' expected, but got {type(amount)}!")

    if amount <= 0:
        raise ValueError("Negative or zero amount value not accepted!")

    if company_code not in ("1001", "1072", "0074"):
        raise ValueError(f"Unrecognized company code: '{company_code}'!")
    
    category = _codes[category_name]["category"]
    reason = _codes[category_name]["reason"]
    acc_fmt = rfc.format_number(int(acc))
    case_type = rfc.get_case_type(company_code)
    sales_org = rfc.get_sales_organization(company_code)

    # Notification header data
    i_riqs5 = {
        'QMART': 'YD',                 # Notification type
        'AUSWIRK': 'YD02',             # Scenario
        'REFNUM': reference_no,        # External reference number
        'QMTXT': desc,                 # Description
        'QMGRP': f"FSCM-{category}",   # Code Group - Coding (FSCM-008)
        'QMCOD': reason,               # Coding
        'FIN_CUSTDISP_AMT': amount,    # Customer disputed amount
        'FIN_CUSTDISP_CUR': 'EUR',     # Customer disputed currency
        'CASE_TYPE': case_type,        # Case type
        'CATEGORY': category,          # Category
        'REASON_CODE': reason,         # Reason
        'ABNUM': 0,                    # Maintenance Plan Call Number
        'SCREENTY': 'O500',            # Scenario or Subscreen Category
        'VKORG': sales_org,            # Sales organization
        'VTWEG': '01',                 # Distribution channel
        'QMKAT': 'D',                  # Catalogue type coding
        'KUNUM': acc_fmt               # Customer account nmber
    }

    # Notification partners (KU = coordinator, WE = ship-to-party, AG = sold-to-party)
    i_ihpa_t = [{
        'PARVW': 'AG',
        'PARNR': acc_fmt,
        'ADRNR': '',
        'REFOBJKEY': '',
    }]

    message1 = rfc.IQS4_CREATE_NOTIFICATION(

        rfc.connection,

        i_qmnum = '',           # Notification number
        i_aufnr = '',           # Order number

        i_post = 'X',            # Post notification
        i_commit = 'X',          # Commit

        i_inlines_t = [],        # Long text
        i_viqmfe_t = [],         # Notification items
        i_viqmur_t = [],         # Notification causes
        i_viqmsm_t = [],         # Notification tasks
        i_viqmma_t = [],         # Notification activities

        i_ihpa_t = i_ihpa_t,
        i_riqs5 = i_riqs5,
    )

    # Check for errors occured while creating QM
    if len(message1['RETURN']) != 0:
        if message1['RETURN'][0]['TYPE'] == 'E':
            raise RuntimeError(message1['RETURN'])

    is_viqmel = {
        'MANDT': '050',                                         # Client
        'QMNUM': message1['E_VIQMEL']['QMNUM'],                 # Notification No
        'MAUEH': 'H',                                           # Unit for Breakdown Duration
        'SCREENTY': 'O500',                                     # Scenario or Subscreen Category
        'QMART': 'YD',                                          # Notification Type
        'QMTXT': desc,                                          # Short Text
        'ARTPR': 'SM',                                          # Priority Type
        'ERNAM': 'G.ROBOT_RFC',                                 # Name of Person Who Created the Object
        'ERDAT': rfc.get_current_time("%Y%m%d"),                # Date on Which Record Was Created
        'AENAM': 'G.ROBOT_RFC',                                 # Name of person who changed object
        'MZEIT': rfc.get_current_time("%H%M%S"),                # Time of Notification
        'QMDAT': rfc.get_current_time("%Y%m%d"),                # Date of Notification
        'STRMN': rfc.get_current_time("%Y%m%d"),                # Required start date
        'STRUR': rfc.get_current_time("%H%M%S"),                # Required Start Time
        'LTRMN': rfc.get_current_time("%Y%m%d"),                # Required End Date
        'LTRUR': rfc.get_current_time("%H%M%S"),                # Requested End Time
        'WAERS': 'EUR',                                         # Currency Key
        'KUNUM': message1['E_VIQMEL']['KUNUM'],                 # Account Number of Customer
        'MAKNZ': 'X',                                           # Task Records Exist
        'OBJNR':  message1['E_VIQMEL']['OBJNR'],                # Object Number for Status Management
        'RBNR': 'YD',                                           # Catalog Profile
        'RBNRI': '0',                                           # Origin of Notifications Catalog Profile
        'KZMLA': 'E',                                           # Primary language indicator for text segment
        'HERKZ': '06',                                          # Origin of Notification
        'BEZDT': rfc.get_current_time("%Y%m%d"),                # Notification Reference Date
        'BEZUR': rfc.get_current_time("%H%M%S"),                # Notification Reference Time
        'SPART': '00',                                          # Division
        'VKORG': sales_org,                                     # Sales Organization
        'BUKRS': company_code,                                  # Company Code
        'VTWEG': '01',                                          # Distribution Channel
        'ERZEIT': rfc.get_current_time("%H%M%S"),               # Time, at Which Record Was Added
        'QMKAT': 'D',                                           # Catalog Type - Coding
        'QMGRP': f"FSCM-{category}",                            # Code Group - Coding (FSCM-008)
        'QMCOD': reason,                                        # Coding
        'REFNUM': reference_no,                                 # External Reference Number
        'HANDLE': message1['E_VIQMEL']['HANDLE'],               # Globally unique identifier (linked to time segment, etc)
        'TZONSO': 'CET',                                        # Time Zone for Notification
        'CASE_TYPE': case_type,                                 # Case Type
        'FIN_CUSTDISP_AMT': amount,                             # Customer-Disputed Amount
        'FIN_CUSTDISP_CUR': 'EUR',                              # Currency of Disputed Amount
        'CATEGORY': category,                                   # Category
        'OWNER': '4',                                           # Object reference indicator
        'AUSWIRK': 'YD02',                                      # Scenario
    }

    # Check partners
    if message1['E_VIQMEL']['ZZ_PARTNER_WE'] == '':
        is_viqmel.update({'ZZ_PARTNER_WE': message1['E_VIQMEL']['KUNUM']})
    else:
        is_viqmel.update({'ZZ_PARTNER_WE': message1['E_VIQMEL']['ZZ_PARTNER_WE']}) # Partner in SD document
        is_viqmel.update({'ZZ_PARTNER_SP': message1['E_VIQMEL']['ZZ_PARTNER_SP']}) # Partner in SD document

    # Create FSCM Dispute
    message2 = rfc.ZQM25_CLAIM_DISPUTE_POST(rfc.connection, is_viqmel)
    case_id = message2['EX_CASE_ID']

    # Read newly created FSCM Dispute
    # Conversion table to get INSTID (SRGBTBREL)
    message3 = rfc.RFC_READ_TABLE(
        rfc.connection,
        query_table = 'SCMG_T_CASE_ATTR',
        options = [{'TEXT': f"EXT_KEY = '{case_id}'"}],
        fields = [{'FIELDNAME': 'CASE_GUID'}],
        rowskips = 0,
        rowcount = 10
    )

    case_guid = message3['DATA'][0]['WA']

    # Ensure the correct reason code an customer account appears in DMS
    rfc.BAPI_DISPUTE_ATTRIBUTES_CHANGE(
        rfc.connection, case_guid,
        attributes = [
            {'ATTR_ID': 'REASON_CODE', 'ATTR_VALUE': reason},
            {'ATTR_ID': 'FIN_KUNNR', 'ATTR_VALUE': acc_fmt},
            {'ATTR_ID': 'ZZ_FILIALE', 'ATTR_VALUE': acc_fmt}
        ]
    )

    notif_id = message1['E_VIQMEL']['QMNUM']

    # enqueue the SN to workflow
    rfc.BAPI_SERVNOT_PUTINPROGRESS(rfc.connection, notif_id)
    
    # Add Task to the SN
    rfc.BAPI_SERVNOT_ADD_DATA(
        rfc.connection,
        number = notif_id,
        notiftask = [{
            'REFOBJECTKEY': message1['E_VIQMEL']['OBJNR'],
            'TASK_KEY': '0001',
            'TASK_SORT_NO': '0001',
            'TASK_TEXT': message2['EX_CASE_ID'],
            'TASK_CODEGRP': 'QYDK0001',
            'TASK_CODE': '0029',
            'PARTN_ROLE': 'VU',
            'PARTNER': 'G.ROBOT_RFC',                                # 'MARTIN.GLEZL'
            'PLND_START_DATE': rfc.get_current_time("%Y%m%d"),       # '20220308'
            'PLND_START_TIME': rfc.get_current_time("%H%M%S"),       # '120000'
            'PLND_END_DATE': rfc.get_current_time("%Y%m%d"),         # '20220308'
            'PLND_END_TIME': rfc.get_current_time("%H%M%S"),         # '120000'
            'CARRIED_OUT_BY': 'G.ROBOT_RFC',
            'ITEM_SORT_NO': '0000',
        }]
    )

    # Complete SN task
    rfc.BAPI_SERVNOT_COMPLETE_TASK(
        rfc.connection,
        number = notif_id,
        task_key = '0001',
        carried_out_by = 'G.ROBOT_RFC',
        carried_out_date = rfc.get_current_time("%Y%m%d"),       # '20220308'
        carried_out_time = rfc.get_current_time("%H%M%S")        # '120000'
    )

    # Complete entire QN
    rfc.BAPI_SERVNOT_CLOSE(rfc.connection, notif_id)

    return (int(notif_id), int(case_id), case_guid)
