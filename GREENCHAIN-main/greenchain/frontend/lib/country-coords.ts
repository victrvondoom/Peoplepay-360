export interface LatLng {
  lat: number
  lng: number
}

export const COUNTRY_CENTROIDS: Record<string, LatLng> = {
  AR: { lat: -38.4161, lng: -63.6167 },
  AT: { lat: 47.5162, lng: 14.5501 },
  AU: { lat: -25.2744, lng: 133.7751 },
  BD: { lat: 23.685, lng: 90.3563 },
  BE: { lat: 50.5039, lng: 4.4699 },
  BR: { lat: -14.235, lng: -51.9253 },
  CA: { lat: 56.1304, lng: -106.3468 },
  CH: { lat: 46.8182, lng: 8.2275 },
  CL: { lat: -35.6751, lng: -71.543 },
  CN: { lat: 35.8617, lng: 104.1954 },
  CZ: { lat: 49.8175, lng: 15.473 },
  DE: { lat: 51.1657, lng: 10.4515 },
  DK: { lat: 56.2639, lng: 9.5018 },
  EG: { lat: 26.8206, lng: 30.8025 },
  ES: { lat: 40.4637, lng: -3.7492 },
  ET: { lat: 9.145, lng: 40.4897 },
  FI: { lat: 61.9241, lng: 25.7482 },
  FR: { lat: 46.2276, lng: 2.2137 },
  GB: { lat: 55.3781, lng: -3.436 },
  GR: { lat: 39.0742, lng: 21.8243 },
  HU: { lat: 47.1625, lng: 19.5033 },
  ID: { lat: -0.7893, lng: 113.9213 },
  IE: { lat: 53.1424, lng: -7.6921 },
  IL: { lat: 31.0461, lng: 34.8516 },
  IN: { lat: 20.5937, lng: 78.9629 },
  IT: { lat: 41.8719, lng: 12.5674 },
  JP: { lat: 36.2048, lng: 138.2529 },
  KE: { lat: -0.0236, lng: 37.9062 },
  KR: { lat: 35.9078, lng: 127.7669 },
  MA: { lat: 31.7917, lng: -7.0926 },
  MX: { lat: 23.6345, lng: -102.5528 },
  MY: { lat: 4.2105, lng: 101.9758 },
  NG: { lat: 9.082, lng: 8.6753 },
  NL: { lat: 52.1326, lng: 5.2913 },
  NO: { lat: 60.472, lng: 8.4689 },
  NZ: { lat: -40.9006, lng: 174.886 },
  PE: { lat: -9.19, lng: -75.0152 },
  PH: { lat: 12.8797, lng: 121.774 },
  PL: { lat: 51.9194, lng: 19.1451 },
  PT: { lat: 39.3999, lng: -8.2245 },
  RO: { lat: 45.9432, lng: 24.9668 },
  RU: { lat: 61.524, lng: 105.3188 },
  SE: { lat: 60.1282, lng: 18.6435 },
  TH: { lat: 15.87, lng: 100.9925 },
  TR: { lat: 38.9637, lng: 35.2433 },
  TW: { lat: 23.6978, lng: 120.9605 },
  UA: { lat: 48.3794, lng: 31.1656 },
  US: { lat: 37.0902, lng: -95.7129 },
  VN: { lat: 14.0583, lng: 108.2772 },
  ZA: { lat: -30.5595, lng: 22.9375 },
  // Additional sourcing countries (backend port table covers these too).
  AE: { lat: 23.4241, lng: 53.8478 },
  AZ: { lat: 40.1431, lng: 47.5769 },
  BG: { lat: 42.7339, lng: 25.4858 },
  BH: { lat: 25.9304, lng: 50.6378 },
  BN: { lat: 4.5353, lng: 114.7277 },
  BO: { lat: -16.2902, lng: -63.5887 },
  CI: { lat: 7.54, lng: -5.5471 },
  CM: { lat: 7.3697, lng: 12.3547 },
  CO: { lat: 4.5709, lng: -74.2973 },
  CR: { lat: 9.7489, lng: -83.7534 },
  CY: { lat: 35.1264, lng: 33.4299 },
  DO: { lat: 18.7357, lng: -70.1627 },
  DZ: { lat: 28.0339, lng: 1.6596 },
  EC: { lat: -1.8312, lng: -78.1834 },
  EE: { lat: 58.5953, lng: 25.0136 },
  GH: { lat: 7.9465, lng: -1.0232 },
  GT: { lat: 15.7835, lng: -90.2308 },
  HK: { lat: 22.3964, lng: 114.1095 },
  HN: { lat: 15.2, lng: -86.2419 },
  HR: { lat: 45.1, lng: 15.2 },
  IQ: { lat: 33.2232, lng: 43.6793 },
  IR: { lat: 32.4279, lng: 53.688 },
  IS: { lat: 64.9631, lng: -19.0208 },
  JM: { lat: 18.1096, lng: -77.2975 },
  JO: { lat: 30.5852, lng: 36.2384 },
  KH: { lat: 12.5657, lng: 104.991 },
  KW: { lat: 29.3117, lng: 47.4818 },
  KZ: { lat: 48.0196, lng: 66.9237 },
  LA: { lat: 19.8563, lng: 102.4955 },
  LB: { lat: 33.8547, lng: 35.8623 },
  LK: { lat: 7.8731, lng: 80.7718 },
  LT: { lat: 55.1694, lng: 23.8813 },
  LU: { lat: 49.8153, lng: 6.1296 },
  LV: { lat: 56.8796, lng: 24.6032 },
  MM: { lat: 21.914, lng: 95.9562 },
  MN: { lat: 46.8625, lng: 103.8467 },
  MT: { lat: 35.9375, lng: 14.3754 },
  MZ: { lat: -18.6657, lng: 35.5296 },
  NI: { lat: 12.8654, lng: -85.2072 },
  NP: { lat: 28.3949, lng: 84.124 },
  OM: { lat: 21.5126, lng: 55.9233 },
  PA: { lat: 8.538, lng: -80.7821 },
  PK: { lat: 30.3753, lng: 69.3451 },
  PY: { lat: -23.4425, lng: -58.4438 },
  QA: { lat: 25.3548, lng: 51.1839 },
  RS: { lat: 44.0165, lng: 21.0059 },
  SA: { lat: 23.8859, lng: 45.0792 },
  SG: { lat: 1.3521, lng: 103.8198 },
  SI: { lat: 46.1512, lng: 14.9955 },
  SK: { lat: 48.669, lng: 19.699 },
  SN: { lat: 14.4974, lng: -14.4524 },
  SV: { lat: 13.7942, lng: -88.8965 },
  TN: { lat: 33.8869, lng: 9.5375 },
  TZ: { lat: -6.369, lng: 34.8888 },
  UG: { lat: 1.3733, lng: 32.2903 },
  UY: { lat: -32.5228, lng: -55.7658 },
  UZ: { lat: 41.3775, lng: 64.5853 },
}

/**
 * English names for every country with a map position. Kept as a static
 * table (not Intl.DisplayNames) so server and browser render identical text.
 */
export const COUNTRY_NAMES: Record<string, string> = {
  AE: "United Arab Emirates",
  AR: "Argentina",
  AT: "Austria",
  AU: "Australia",
  AZ: "Azerbaijan",
  BD: "Bangladesh",
  BE: "Belgium",
  BG: "Bulgaria",
  BH: "Bahrain",
  BN: "Brunei",
  BO: "Bolivia",
  BR: "Brazil",
  CA: "Canada",
  CH: "Switzerland",
  CI: "Côte d'Ivoire",
  CL: "Chile",
  CM: "Cameroon",
  CN: "China",
  CO: "Colombia",
  CR: "Costa Rica",
  CY: "Cyprus",
  CZ: "Czechia",
  DE: "Germany",
  DK: "Denmark",
  DO: "Dominican Republic",
  DZ: "Algeria",
  EC: "Ecuador",
  EE: "Estonia",
  EG: "Egypt",
  ES: "Spain",
  ET: "Ethiopia",
  FI: "Finland",
  FR: "France",
  GB: "United Kingdom",
  GH: "Ghana",
  GR: "Greece",
  GT: "Guatemala",
  HK: "Hong Kong",
  HN: "Honduras",
  HR: "Croatia",
  HU: "Hungary",
  ID: "Indonesia",
  IE: "Ireland",
  IL: "Israel",
  IN: "India",
  IQ: "Iraq",
  IR: "Iran",
  IS: "Iceland",
  IT: "Italy",
  JM: "Jamaica",
  JO: "Jordan",
  JP: "Japan",
  KE: "Kenya",
  KH: "Cambodia",
  KR: "South Korea",
  KW: "Kuwait",
  KZ: "Kazakhstan",
  LA: "Laos",
  LB: "Lebanon",
  LK: "Sri Lanka",
  LT: "Lithuania",
  LU: "Luxembourg",
  LV: "Latvia",
  MA: "Morocco",
  MM: "Myanmar",
  MN: "Mongolia",
  MT: "Malta",
  MX: "Mexico",
  MY: "Malaysia",
  MZ: "Mozambique",
  NG: "Nigeria",
  NI: "Nicaragua",
  NL: "Netherlands",
  NO: "Norway",
  NP: "Nepal",
  NZ: "New Zealand",
  OM: "Oman",
  PA: "Panama",
  PE: "Peru",
  PH: "Philippines",
  PK: "Pakistan",
  PL: "Poland",
  PT: "Portugal",
  PY: "Paraguay",
  QA: "Qatar",
  RO: "Romania",
  RS: "Serbia",
  RU: "Russia",
  SA: "Saudi Arabia",
  SE: "Sweden",
  SG: "Singapore",
  SI: "Slovenia",
  SK: "Slovakia",
  SN: "Senegal",
  SV: "El Salvador",
  TH: "Thailand",
  TN: "Tunisia",
  TR: "Türkiye",
  TW: "Taiwan",
  TZ: "Tanzania",
  UA: "Ukraine",
  UG: "Uganda",
  US: "United States",
  UY: "Uruguay",
  UZ: "Uzbekistan",
  VN: "Vietnam",
  ZA: "South Africa",
}

let regionNames: Intl.DisplayNames | null | undefined

/** Display name for an ISO-2 code; falls back to Intl, then the code itself. */
export function getCountryName(countryCode: string): string {
  const code = countryCode.trim().toUpperCase()
  if (COUNTRY_NAMES[code]) {
    return COUNTRY_NAMES[code]
  }
  if (regionNames === undefined) {
    try {
      regionNames = new Intl.DisplayNames(["en"], { type: "region" })
    } catch {
      regionNames = null
    }
  }
  try {
    return regionNames?.of(code) ?? code
  } catch {
    return code
  }
}

export interface CountryOption {
  code: string
  name: string
}

let countryOptions: CountryOption[] | null = null

/** Countries that can be placed on the map, sorted by name. */
export function getCountryOptions(): CountryOption[] {
  if (!countryOptions) {
    countryOptions = Object.keys(COUNTRY_CENTROIDS)
      .map((code) => ({ code, name: COUNTRY_NAMES[code] ?? code }))
      .sort((left, right) => left.name.localeCompare(right.name, "en"))
  }
  return countryOptions
}

export function getCountryCentroid(countryCode: string): LatLng {
  const code = countryCode.trim().toUpperCase()
  const centroid = COUNTRY_CENTROIDS[code]
  if (!centroid) {
    if (typeof console !== "undefined") {
      console.warn(
        `[country-coords] No centroid for ISO-2 "${code}"; falling back to {0, 0}`
      )
    }
    return { lat: 0, lng: 0 }
  }
  return centroid
}
