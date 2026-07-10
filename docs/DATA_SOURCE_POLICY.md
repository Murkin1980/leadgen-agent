# Data Source Policy

## Overview
This document describes the data sources used by the Leadgen Agent and the policies governing their use.

## Supported Data Sources

### 1. Mock Provider
- **Status**: Always available
- **Purpose**: Development, testing, and CI/CD
- **Data**: Static test data (6 companies)
- **Rate Limits**: None
- **API Key**: Not required

### 2. CSV Provider
- **Status**: Always available
- **Purpose**: Importing real company data from CSV files
- **Data**: User-provided CSV files
- **Rate Limits**: None
- **API Key**: Not required
- **File Location**: `import/companies.csv`

### 3. 2GIS API Provider
- **Status**: Requires API key
- **Purpose**: Collecting company data from 2GIS directory
- **Data**: Real company listings
- **Rate Limits**: Subject to 2GIS API limits
- **API Key**: Required (`TWO_GIS_API_KEY`)

## Data Collection Rules

### Acceptance Criteria
A lead is accepted if it meets ALL of the following:
1. Has a valid phone number
2. Does NOT have a website (or website is unreachable)
3. Has a non-empty company name
4. Passes qualification scoring (score >= `LEAD_MIN_SCORE`)

### Website Verification
- Websites are checked for reachability
- SSRF protection blocks private/internal IPs
- Companies with working websites are rejected for landing page creation

### Lead Qualification Scoring
| Factor | Points |
|--------|--------|
| Has phone | +20 |
| Has website | -30 |
| Has Instagram | +15 |
| Rating >= 4.0 | +20 |
| Rating >= 3.0 | +10 |
| Reviews >= 10 | +15 |

**Minimum Score**: 50 (configurable via `LEAD_MIN_SCORE`)

## Terms of Service Compliance

### 2GIS API
- Use only official API endpoints
- Respect rate limits
- Do not bypass CAPTCHAs or IP blocks
- Do not use proxy rotation
- Do not scrape HTML pages directly

### CSV Import
- User is responsible for data legality
- No automated web scraping
- Data should be publicly available business information

## Data Storage

### Database
- All leads stored in PostgreSQL
- Source tracking: `provider` + `source_id`
- Deduplication: Unique constraint on `(source, source_id)`

### Files
- Landing pages stored in `sites/public/`
- CSV files stored in `import/`
- No sensitive data in logs

## Security

### SSRF Protection
- Website verification blocks private IPs (10.x, 172.16-31.x, 192.168.x)
- Blocks localhost, .local domains
- DNS resolution checked before HTTP requests

### API Keys
- Stored in environment variables
- Never logged or committed to git
- Rotated regularly in production

### Rate Limiting
- HTTP requests to external APIs use exponential backoff
- Maximum retry attempts configurable
- No parallel requests to same endpoint
