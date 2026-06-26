"""
international_funds.py — 25 Indian-domiciled international/global FoFs
Covers: US Broad, US Tech, European, Asian, Global Thematic
All SEBI-registered, available on Groww/Zerodha/Kuvera
"""

INTL_SNAPSHOT_DATE = "Jun 2026"

INTL_SCHEMES = {
    -1001: {"family_id": -1001, "name": "Motilal Oswal Nasdaq 100 FoF", "category": "International - US Tech", "amc": "Motilal Oswal Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 8.8, "Microsoft Corp": 8.2, "NVIDIA Corp": 7.5, "Amazon.com Inc": 5.4, "Broadcom Inc": 4.8, "Meta Platforms Inc": 4.5, "Alphabet Inc Class A": 3.8, "Alphabet Inc Class C": 3.6, "Tesla Inc": 3.2, "Costco Wholesale Corp": 2.8, "Netflix Inc": 2.5, "Adobe Inc": 2.2, "Advanced Micro Devices Inc": 2.0, "T-Mobile US Inc": 1.8, "Qualcomm Inc": 1.6,
    }},
    -1002: {"family_id": -1002, "name": "ICICI Prudential US Bluechip Equity Fund", "category": "International - US Broad", "amc": "ICICI Prudential Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 7.2, "Microsoft Corp": 6.8, "NVIDIA Corp": 5.5, "Amazon.com Inc": 4.8, "Alphabet Inc Class A": 4.2, "Meta Platforms Inc": 3.8, "Berkshire Hathaway Inc": 3.5, "JPMorgan Chase & Co": 3.2, "UnitedHealth Group Inc": 2.8, "Eli Lilly and Co": 2.5, "Visa Inc": 2.2, "Johnson & Johnson": 2.0, "Procter & Gamble Co": 1.8, "Mastercard Inc": 1.6, "Walmart Inc": 1.5,
    }},
    -1003: {"family_id": -1003, "name": "Motilal Oswal S&P 500 Index Fund", "category": "International - US Broad", "amc": "Motilal Oswal Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 7.0, "Microsoft Corp": 6.5, "NVIDIA Corp": 6.2, "Amazon.com Inc": 4.0, "Alphabet Inc Class A": 3.5, "Meta Platforms Inc": 2.8, "Berkshire Hathaway Inc": 2.5, "Broadcom Inc": 2.2, "JPMorgan Chase & Co": 2.0, "Tesla Inc": 1.8, "UnitedHealth Group Inc": 1.5, "Eli Lilly and Co": 1.4, "Visa Inc": 1.2, "Johnson & Johnson": 1.1, "Walmart Inc": 1.0,
    }},
    -1004: {"family_id": -1004, "name": "Franklin India Feeder - US Opportunities Fund", "category": "International - US Broad", "amc": "Franklin Templeton Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Microsoft Corp": 5.5, "Amazon.com Inc": 4.8, "Apple Inc": 4.2, "Alphabet Inc Class A": 3.8, "UnitedHealth Group Inc": 3.5, "NVIDIA Corp": 3.2, "Visa Inc": 2.8, "Mastercard Inc": 2.5, "Eli Lilly and Co": 2.2, "ServiceNow Inc": 2.0, "Salesforce Inc": 1.8, "Intuit Inc": 1.6, "Palo Alto Networks Inc": 1.5, "Uber Technologies Inc": 1.4, "Booking Holdings Inc": 1.2,
    }},
    -1005: {"family_id": -1005, "name": "Mirae Asset NYSE FANG+ ETF FoF", "category": "International - US Tech", "amc": "Mirae Asset Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "NVIDIA Corp": 10.2, "Meta Platforms Inc": 9.8, "Alphabet Inc Class A": 9.5, "Amazon.com Inc": 9.2, "Apple Inc": 9.0, "Microsoft Corp": 8.8, "Netflix Inc": 8.5, "Broadcom Inc": 8.2, "Tesla Inc": 7.8, "Snowflake Inc": 7.5, "CrowdStrike Holdings Inc": 5.8,
    }},
    -1006: {"family_id": -1006, "name": "Edelweiss US Technology Equity FoF", "category": "International - US Tech", "amc": "Edelweiss Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 9.5, "Microsoft Corp": 8.8, "NVIDIA Corp": 7.2, "Alphabet Inc Class A": 5.5, "Amazon.com Inc": 4.8, "Meta Platforms Inc": 4.2, "Broadcom Inc": 3.8, "Adobe Inc": 3.2, "Salesforce Inc": 2.8, "Advanced Micro Devices Inc": 2.5, "ServiceNow Inc": 2.2, "Intuit Inc": 1.8, "Palo Alto Networks Inc": 1.5,
    }},
    -1007: {"family_id": -1007, "name": "ICICI Prudential Nasdaq 100 Index Fund", "category": "International - US Tech", "amc": "ICICI Prudential Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 8.5, "Microsoft Corp": 8.0, "NVIDIA Corp": 7.8, "Amazon.com Inc": 5.2, "Broadcom Inc": 4.5, "Meta Platforms Inc": 4.2, "Alphabet Inc Class A": 3.5, "Alphabet Inc Class C": 3.4, "Tesla Inc": 3.0, "Costco Wholesale Corp": 2.6, "Netflix Inc": 2.4, "Adobe Inc": 2.0, "AMD Inc": 1.8, "T-Mobile US Inc": 1.6,
    }},
    -1008: {"family_id": -1008, "name": "Kotak Nasdaq 100 FoF", "category": "International - US Tech", "amc": "Kotak Mahindra Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 8.6, "Microsoft Corp": 8.1, "NVIDIA Corp": 7.6, "Amazon.com Inc": 5.3, "Broadcom Inc": 4.6, "Meta Platforms Inc": 4.3, "Alphabet Inc Class A": 3.6, "Tesla Inc": 3.1, "Costco Wholesale Corp": 2.7, "Netflix Inc": 2.5, "Adobe Inc": 2.1, "AMD Inc": 1.9, "Qualcomm Inc": 1.7,
    }},
    -1009: {"family_id": -1009, "name": "Edelweiss Europe Dynamic Equity Offshore Fund", "category": "International - Europe", "amc": "Edelweiss Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "ASML Holding NV": 5.8, "Novo Nordisk A/S": 5.2, "SAP SE": 4.5, "LVMH Moet Hennessy": 4.0, "Nestle SA": 3.5, "Roche Holding AG": 3.2, "AstraZeneca PLC": 3.0, "Shell PLC": 2.8, "Siemens AG": 2.5, "TotalEnergies SE": 2.2, "Schneider Electric SE": 2.0, "Sanofi SA": 1.8, "Unilever PLC": 1.5, "Allianz SE": 1.2,
    }},
    -1010: {"family_id": -1010, "name": "ABSL International Equity Fund", "category": "International - Global", "amc": "Aditya Birla Sun Life Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Microsoft Corp": 5.0, "Apple Inc": 4.5, "NVIDIA Corp": 3.8, "Amazon.com Inc": 3.2, "ASML Holding NV": 2.8, "Alphabet Inc Class A": 2.5, "Novo Nordisk A/S": 2.2, "TSMC": 2.0, "Samsung Electronics": 1.8, "Meta Platforms Inc": 1.6, "JPMorgan Chase & Co": 1.5, "Nestle SA": 1.2, "Toyota Motor Corp": 1.0,
    }},
    -1011: {"family_id": -1011, "name": "DSP Global Innovation FoF", "category": "International - Global Thematic", "amc": "DSP Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "NVIDIA Corp": 6.5, "Microsoft Corp": 5.8, "Amazon.com Inc": 4.5, "Tesla Inc": 4.0, "Apple Inc": 3.5, "Alphabet Inc Class A": 3.2, "ASML Holding NV": 2.8, "Broadcom Inc": 2.5, "AMD Inc": 2.2, "ServiceNow Inc": 2.0, "Palo Alto Networks Inc": 1.8, "CrowdStrike Holdings Inc": 1.5, "Snowflake Inc": 1.2,
    }},
    -1012: {"family_id": -1012, "name": "Nippon India Japan Equity Fund", "category": "International - Japan", "amc": "Nippon India Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Toyota Motor Corp": 6.8, "Sony Group Corp": 5.5, "Mitsubishi UFJ Financial": 4.8, "Keyence Corp": 4.2, "Tokyo Electron Ltd": 3.8, "Hitachi Ltd": 3.5, "Shin-Etsu Chemical": 3.0, "Recruit Holdings": 2.8, "Daikin Industries": 2.5, "Nintendo Co Ltd": 2.2, "Fast Retailing Co": 2.0, "SoftBank Group": 1.8, "Sumitomo Mitsui Financial": 1.5,
    }},
    -1013: {"family_id": -1013, "name": "Franklin Asian Equity Fund", "category": "International - Asia", "amc": "Franklin Templeton Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "TSMC": 8.5, "Samsung Electronics": 6.2, "Tencent Holdings": 5.5, "Alibaba Group": 4.8, "AIA Group": 3.5, "Toyota Motor Corp": 3.0, "Sony Group Corp": 2.5, "Keyence Corp": 2.2, "BHP Group": 2.0, "Commonwealth Bank of Australia": 1.8, "Meituan": 1.5, "JD.com Inc": 1.2, "Sea Ltd": 1.0,
    }},
    -1014: {"family_id": -1014, "name": "PGIM India Global Equity Opportunities Fund", "category": "International - Global", "amc": "PGIM India Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Microsoft Corp": 5.5, "Apple Inc": 4.8, "NVIDIA Corp": 4.2, "Amazon.com Inc": 3.8, "Alphabet Inc Class A": 3.2, "UnitedHealth Group Inc": 2.8, "Eli Lilly and Co": 2.5, "JPMorgan Chase & Co": 2.2, "Visa Inc": 2.0, "ASML Holding NV": 1.8, "Novo Nordisk A/S": 1.5, "TSMC": 1.4, "Samsung Electronics": 1.2,
    }},
    -1015: {"family_id": -1015, "name": "Kotak Global Innovation FoF", "category": "International - Global Thematic", "amc": "Kotak Mahindra Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "NVIDIA Corp": 6.0, "Microsoft Corp": 5.5, "Apple Inc": 4.8, "Amazon.com Inc": 4.0, "Alphabet Inc Class A": 3.5, "Tesla Inc": 3.0, "ASML Holding NV": 2.5, "Broadcom Inc": 2.2, "AMD Inc": 2.0, "Meta Platforms Inc": 1.8, "ServiceNow Inc": 1.5, "Palo Alto Networks Inc": 1.2,
    }},
    -1016: {"family_id": -1016, "name": "Motilal Oswal MSCI EAFE Top 100 Select Index Fund", "category": "International - Developed ex-US", "amc": "Motilal Oswal Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "ASML Holding NV": 5.0, "Novo Nordisk A/S": 4.5, "LVMH Moet Hennessy": 3.8, "SAP SE": 3.2, "Toyota Motor Corp": 3.0, "Nestle SA": 2.8, "AstraZeneca PLC": 2.5, "Shell PLC": 2.2, "Roche Holding AG": 2.0, "TSMC": 1.8, "Samsung Electronics": 1.6, "Siemens AG": 1.5, "Unilever PLC": 1.2, "Sony Group Corp": 1.0,
    }},
    -1017: {"family_id": -1017, "name": "SBI International Access - US Equity FoF", "category": "International - US Broad", "amc": "SBI Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 7.0, "Microsoft Corp": 6.5, "NVIDIA Corp": 5.8, "Amazon.com Inc": 4.2, "Alphabet Inc Class A": 3.8, "Meta Platforms Inc": 3.2, "Berkshire Hathaway Inc": 2.8, "JPMorgan Chase & Co": 2.5, "UnitedHealth Group Inc": 2.2, "Eli Lilly and Co": 2.0, "Visa Inc": 1.8, "Mastercard Inc": 1.5, "Procter & Gamble Co": 1.2,
    }},
    -1018: {"family_id": -1018, "name": "HDFC Developed World Indexes FoF", "category": "International - Global", "amc": "HDFC Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 5.5, "Microsoft Corp": 5.0, "NVIDIA Corp": 4.2, "Amazon.com Inc": 3.5, "Alphabet Inc Class A": 2.8, "Meta Platforms Inc": 2.2, "ASML Holding NV": 1.8, "Novo Nordisk A/S": 1.5, "TSMC": 1.4, "Toyota Motor Corp": 1.2, "Nestle SA": 1.0, "Samsung Electronics": 0.9, "JPMorgan Chase & Co": 0.8,
    }},
    -1019: {"family_id": -1019, "name": "Axis Global Equity Alpha FoF", "category": "International - Global", "amc": "Axis Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Microsoft Corp": 5.8, "Apple Inc": 5.0, "NVIDIA Corp": 4.5, "Amazon.com Inc": 3.8, "Alphabet Inc Class A": 3.2, "Eli Lilly and Co": 2.8, "UnitedHealth Group Inc": 2.5, "Visa Inc": 2.2, "ASML Holding NV": 2.0, "Novo Nordisk A/S": 1.8, "TSMC": 1.5, "Mastercard Inc": 1.2,
    }},
    -1020: {"family_id": -1020, "name": "Bandhan US Equity FoF", "category": "International - US Broad", "amc": "Bandhan Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Apple Inc": 7.2, "Microsoft Corp": 6.8, "NVIDIA Corp": 5.5, "Amazon.com Inc": 4.5, "Alphabet Inc Class A": 3.8, "Meta Platforms Inc": 3.2, "Berkshire Hathaway Inc": 2.8, "JPMorgan Chase & Co": 2.5, "UnitedHealth Group Inc": 2.0, "Eli Lilly and Co": 1.8, "Visa Inc": 1.5, "Johnson & Johnson": 1.2,
    }},
    -1021: {"family_id": -1021, "name": "Invesco India - Invesco Global Consumer Trends FoF", "category": "International - Global Thematic", "amc": "Invesco Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Amazon.com Inc": 6.5, "LVMH Moet Hennessy": 5.0, "Nike Inc": 4.2, "Hermes International": 3.8, "Ferrari NV": 3.5, "Booking Holdings Inc": 3.0, "MercadoLibre Inc": 2.8, "Meituan": 2.5, "Estee Lauder Companies": 2.2, "Lululemon Athletica Inc": 2.0, "Spotify Technology": 1.8, "Pinduoduo Inc": 1.5,
    }},
    -1022: {"family_id": -1022, "name": "Nippon India Taiwan Equity Fund", "category": "International - Taiwan", "amc": "Nippon India Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "TSMC": 28.5, "MediaTek Inc": 5.8, "Hon Hai Precision": 4.5, "Delta Electronics": 3.8, "Fubon Financial": 3.2, "Cathay Financial": 2.8, "United Microelectronics": 2.5, "Quanta Computer": 2.2, "ASE Technology": 2.0, "Chunghwa Telecom": 1.8,
    }},
    -1023: {"family_id": -1023, "name": "Kotak International REIT FoF", "category": "International - REITs", "amc": "Kotak Mahindra Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Prologis Inc": 8.5, "American Tower Corp": 7.2, "Equinix Inc": 6.0, "Crown Castle Inc": 4.5, "Public Storage": 4.0, "Simon Property Group": 3.5, "Digital Realty Trust": 3.2, "Realty Income Corp": 3.0, "Welltower Inc": 2.5, "VICI Properties": 2.2,
    }},
    -1024: {"family_id": -1024, "name": "ICICI Prudential Global Stable Equity Fund", "category": "International - Global", "amc": "ICICI Prudential Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Johnson & Johnson": 4.5, "Procter & Gamble Co": 4.0, "Nestle SA": 3.8, "Roche Holding AG": 3.5, "Novartis AG": 3.2, "PepsiCo Inc": 3.0, "Coca-Cola Co": 2.8, "Unilever PLC": 2.5, "Colgate-Palmolive Co": 2.2, "Walmart Inc": 2.0, "McDonald's Corp": 1.8, "Diageo PLC": 1.5,
    }},
    -1025: {"family_id": -1025, "name": "Mirae Asset Hang Seng TECH ETF FoF", "category": "International - China Tech", "amc": "Mirae Asset Mutual Fund", "month": INTL_SNAPSHOT_DATE, "holdings": {
        "Alibaba Group": 8.5, "Tencent Holdings": 8.0, "Meituan": 6.5, "JD.com Inc": 5.5, "Xiaomi Corp": 5.0, "BYD Co": 4.5, "Baidu Inc": 4.0, "NetEase Inc": 3.5, "Kuaishou Technology": 3.0, "Li Auto Inc": 2.8, "NIO Inc": 2.2, "Bilibili Inc": 1.8,
    }},
}
