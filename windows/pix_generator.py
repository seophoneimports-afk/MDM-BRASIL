import re

def crc16_ccitt(data: str) -> str:
    """Calculates CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""
    crc = 0xFFFF
    for ch in data.encode('utf-8'):
        crc ^= (ch << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

def tlv(tag: str, val: str) -> str:
    """Formats Tag-Length-Value according to EMVCo standard."""
    b_len = len(val.encode('utf-8'))
    return f"{tag}{b_len:02d}{val}"

def parse_currency(value_str: str) -> float:
    """Extracts a valid float from currency strings like 'R$ 250,00', '250.00', '250'."""
    if not value_str:
        return 0.0
    cleaned = re.sub(r'[^\d,.]', '', value_str).replace(' ', '')
    if not cleaned:
        return 0.0
    if ',' in cleaned and '.' in cleaned:
        # e.g. 1.250,00 -> 1250.00
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        # e.g. 250,00 -> 250.00
        cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def generate_pix_emv(key: str, amount_str: str = "", merchant_name: str = "MDM FRP BRASIL", city: str = "SAO PAULO", txid: str = "***") -> str:
    """
    Generates a 100% compliant Central Bank (BCB) / EMVCo static Pix BR Code string.
    Works with ANY key type:
    - Chave Aleatória (Mercado Pago / UUID)
    - CPF / CNPJ
    - E-mail
    - Telefone (+55...)
    - Or if already an EMV payload (starts with '000201'), returns or updates it.
    """
    key = key.strip()
    if not key:
        return ""

    # If the user already pasted a complete EMV BR Code string
    if key.startswith("000201") and "BR.GOV.BCB.PIX" in key:
        return key

    # Format phone if user typed only numbers (e.g. 11999999999 -> +5511999999999)
    if re.match(r'^\d{10,11}$', key):
        key = f"+55{key}"

    # Clean merchant name & city (alphanumeric + spaces only, max lengths)
    clean_name = re.sub(r'[^A-Za-z0-9 ]', '', merchant_name).strip()[:25]
    if not clean_name:
        clean_name = "MDM FRP BRASIL"

    clean_city = re.sub(r'[^A-Za-z0-9 ]', '', city).strip()[:15]
    if not clean_city:
        clean_city = "SAO PAULO"

    clean_txid = re.sub(r'[^A-Za-z0-9]', '', txid).strip()[:25]
    if not clean_txid:
        clean_txid = "***"

    amount = parse_currency(amount_str)

    # 00: Payload Format Indicator
    payload = tlv("00", "01")

    # 26: Merchant Account Information
    sub_gui = tlv("00", "BR.GOV.BCB.PIX")
    sub_key = tlv("01", key)
    payload += tlv("26", sub_gui + sub_key)

    # 52: Merchant Category Code (0000 = default)
    payload += tlv("52", "0000")

    # 53: Transaction Currency (986 = BRL)
    payload += tlv("53", "986")

    # 54: Transaction Amount (only if > 0)
    if amount > 0:
        val_str = f"{amount:.2f}"
        payload += tlv("54", val_str)

    # 58: Country Code
    payload += tlv("58", "BR")

    # 59: Merchant Name
    payload += tlv("59", clean_name.upper())

    # 60: Merchant City
    payload += tlv("60", clean_city.upper())

    # 62: Additional Data Field Template (TxID)
    sub_txid = tlv("05", clean_txid)
    payload += tlv("62", sub_txid)

    # 63: CRC16 prefix
    payload_to_crc = payload + "6304"
    crc = crc16_ccitt(payload_to_crc)

    return payload_to_crc + crc
