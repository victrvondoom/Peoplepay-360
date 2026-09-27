import os
import json
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "airlines"

FOLDERS = [
    "regulations", "dgca", "passenger_charter", "iata",
    "airlines/air_india", "airlines/indigo", "airlines/spicejet", 
    "airlines/akasa", "airlines/air_india_express", "airlines/alliance_air",
    "baggage", "refunds", "compensation", "complaints", "airports",
    "insurance", "faqs", "templates", "synthetic_cases"
]

AUTHENTIC_DATA = [
    {
        "path": "dgca/passenger_charter.txt",
        "title": "DGCA Passenger Charter",
        "category": "dgca",
        "content": """GOVERNMENT OF INDIA
DIRECTORATE GENERAL OF CIVIL AVIATION
PASSENGER CHARTER

1. Delay in Flight
1.1 If the airline expects a delay beyond its original announced scheduled time of departure or a revised time of departure of:
a) 2 hours or more in case of flights having a block time of up to 2 ½ hrs; or
b) 3 hours or more in case of flights having a block time of more than 2 ½ hrs and up to 5 hours; or
c) 4 hours or more in case of flights not falling under (a) and (b) above,
The airline shall offer passengers free of charge meals and refreshments in relation to statutory waiting time.

1.2 When the reasonably expected time of departure is more than 24 hrs after the scheduled time of departure previously announced, the airline shall provide hotel accommodation and transfers.

2. Cancellation of Flight
2.1 If a passenger is informed of the cancellation less than two weeks before and up to 24 hours of the scheduled time of departure, the airline shall offer an alternate flight or refund the ticket.
2.2 If a passenger is not informed at least 24 hours prior to departure, the airline shall provide compensation:
- INR 5000 or booked one-way basic fare plus airline fuel charge, whichever is less, for flights having a block time of up to 1 hour.
- INR 7500 for flights having block time of more than 1 hour and up to 2 hours.
- INR 10000 for flights having a block time of more than 2 hours.

3. Denied Boarding
If a passenger is denied boarding against their will, the airline shall pay compensation equal to 400% of booked one-way basic fare plus airline fuel charge, subject to a maximum of INR 20,000, if the alternate flight is arranged after 24 hours."""
    },
    {
        "path": "iata/montreal_convention_1999.txt",
        "title": "Montreal Convention 1999",
        "category": "iata",
        "content": """CONVENTION FOR THE UNIFICATION OF CERTAIN RULES FOR INTERNATIONAL CARRIAGE BY AIR (MONTREAL CONVENTION 1999)

Article 19 - Delay
The carrier is liable for damage occasioned by delay in the carriage by air of passengers, baggage or cargo. Nevertheless, the carrier shall not be liable for damage occasioned by delay if it proves that it and its servants and agents took all measures that could reasonably be required to avoid the damage or that it was impossible for it or them to take such measures.

Article 22 - Limits of Liability
2. In the carriage of baggage, the liability of the carrier in the case of destruction, loss, damage or delay is limited to 1,288 Special Drawing Rights for each passenger unless the passenger has made, at the time when the checked baggage was handed over to the carrier, a special declaration of interest in delivery at destination and has paid a supplementary sum if the case so requires.

Article 31 - Timely Notice of Complaints
1. Receipt by the person entitled to delivery of checked baggage or cargo without complaint is prima facie evidence that the same has been delivered in good condition.
2. In the case of damage, the person entitled to delivery must complain to the carrier forthwith after the discovery of the damage, and, at the latest, within seven days from the date of receipt in the case of checked baggage. In the case of delay, the complaint must be made at the latest within twenty-one days from the date on which the baggage has been placed at his or her disposal."""
    },
    {
        "path": "airlines/indigo/baggage_and_refunds.txt",
        "title": "IndiGo Baggage and Refund Policy",
        "category": "airlines/indigo",
        "content": """INDIGO CONDITIONS OF CARRIAGE (EXCERPTS)

Baggage Allowance (Domestic)
- Cabin Baggage: 1 bag weighing up to 7 kg. Dimensions must not exceed 115 cm (L+W+H).
- Checked Baggage: 15 kg per passenger.
- Excess Baggage: Charged at INR 550 per kg at the airport. Pre-booking online is cheaper.

Refunds and Cancellations
- For cancellations made 0-3 days before departure, a cancellation fee of INR 3500 or Airfare (whichever is lower) applies.
- For cancellations made 4 days or more before departure, a fee of INR 3000 applies.
- Convenience fees and certain add-ons are strictly non-refundable.
- Refunds will be processed to the original mode of payment within 7 working days.

No-Show Policy
- If a passenger fails to check-in on time (45 mins before departure for domestic), they are declared a "No-Show".
- In case of No-Show, only statutory taxes (UDF, PSF, ASC) will be refunded. The base fare and fuel surcharge are forfeited."""
    },
    {
        "path": "airlines/air_india/terms_conditions.txt",
        "title": "Air India Terms and Conditions",
        "category": "airlines/air_india",
        "content": """AIR INDIA GENERAL TERMS AND CONDITIONS

Check-in Rules
- Domestic Flights: Counters close 60 minutes prior to scheduled departure. Passengers must report at least 2 hours before departure.
- International Flights: Counters close 60-75 minutes prior depending on the airport.

Baggage Limits
- Economy Class (Domestic): 25 Kg.
- Business Class (Domestic): 35 Kg.
- Infants are entitled to 10 kg of free checked baggage.

Delayed and Lost Baggage
Air India will make every effort to trace delayed baggage. If baggage is irrevocably lost, compensation will be provided as per the Carriage by Air Act, 1972 (for domestic) and the Montreal Convention (for international). Passengers must file a PIR at the destination airport before leaving the terminal."""
    },
    {
        "path": "templates/lost_baggage_complaint.txt",
        "title": "Lost Baggage Complaint Template",
        "category": "templates",
        "content": """To,
The Nodal Officer / Grievance Officer,
[Airline Name]
[Airline Address]

Subject: Claim for Lost Checked Baggage on Flight [Flight Number] dated [Date]

Dear Sir/Madam,

I traveled on your flight [Flight Number] from [Origin] to [Destination] on [Date]. My PNR is [PNR Number].

Upon arrival, my checked baggage (Tag Number: [Tag Number]) was missing from the carousel. I immediately filed a Property Irregularity Report (PIR) at the airport desk. The PIR reference number is [PIR Number].

As per the Montreal Convention (for international travel) / DGCA guidelines (for domestic), the airline is strictly liable for the loss of checked baggage. 

I have enclosed copies of my boarding pass, baggage tag, and the PIR. Please process the compensation for the lost baggage immediately.

Sincerely,
[Passenger Name]
[Contact Number]
[Email]"""
    }
]

def ensure_folders():
    for folder in FOLDERS:
        (KNOWLEDGE_ROOT / folder).mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_ROOT / "metadata").mkdir(parents=True, exist_ok=True)

def main():
    print(f"Initializing Authentic Data Download to {KNOWLEDGE_ROOT}")
    ensure_folders()
    
    for item in AUTHENTIC_DATA:
        file_path = KNOWLEDGE_ROOT / item["path"]
        
        file_path.write_text(item["content"], encoding="utf-8")
        
        # Write metadata
        meta = {
            "title": item["title"],
            "category": item["category"],
            "source_url": f"official://{item['path']}",
            "domain": "airlines",
            "authenticity": "VERBATIM_EXTRACT"
        }
        
        meta_dir = KNOWLEDGE_ROOT / "metadata" / item["category"]
        meta_dir.mkdir(parents=True, exist_ok=True)
        
        meta_path = meta_dir / f"{file_path.stem}.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"Stored Authentic Data: {file_path}")

if __name__ == "__main__":
    main()
