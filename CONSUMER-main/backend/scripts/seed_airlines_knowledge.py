import os
from pathlib import Path
import json

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "airlines"

# Extensive airline knowledge data
LARGE_DOCUMENTS = [
    {
        "path": "dgca/passenger_charter.md",
        "title": "DGCA Passenger Charter - Rights of Passengers",
        "authority": "DGCA",
        "category": "dgca",
        "content": """# DGCA Passenger Charter

## 1. Flight Delays
1.1. In case of flight delay, airlines are required to provide free meals and refreshments in relation to statutory waiting time.
1.2. If a domestic flight is expected to be delayed by more than 6 hours, the airline must inform the passenger at least 24 hours prior to the scheduled departure. The airline must offer an option of a full refund or an alternative flight.
1.3. For delays between 24 hours or more, airlines must provide hotel accommodation (including transfers) free of charge.

## 2. Flight Cancellations
2.1. If an airline cancels a flight and fails to inform the passenger at least 2 weeks before scheduled departure, the airline must provide compensation.
2.2. Compensation for cancellations:
- INR 5,000 or booked one-way basic fare plus airline fuel charge, whichever is less for flights having a block time of up to and including 1 hour.
- INR 7,500 for flights between 1 and 2 hours.
- INR 10,000 for flights beyond 2 hours.

## 3. Denied Boarding (Overbooking)
3.1. If a passenger is denied boarding despite having a confirmed ticket and presenting themselves for check-in on time, the airline must first ask for volunteers to give up their seats.
3.2. If boarding is denied against the passenger's will, the airline must pay compensation equal to 400% of the booked one-way basic fare plus airline fuel charge, subject to a maximum of INR 20,000.
""" * 5
    },
    {
        "path": "regulations/car_section_3_series_m_part_iv.md",
        "title": "Civil Aviation Requirements - Facilities to be provided to passengers",
        "authority": "DGCA",
        "category": "regulations",
        "content": """# Civil Aviation Requirement (CAR) Section 3, Series M, Part IV

## 3. Refunds
3.1. Airlines shall refund all statutory taxes and User Development Fee (UDF), Passenger Service Fee (PSF), and Airport Development Fee (ADF) to the passengers in case of cancellation/non-utilization of tickets/no show. This provision applies to all types of fares, including non-refundable promotional fares.
3.2. The cancellation charges shall not be more than the basic fare plus fuel surcharge. The airline cannot charge an additional cancellation fee.
3.3. Refunds must be processed within 7 working days for credit card payments and immediately for cash payments made at airline counters.

## 4. Name Correction
4.1. Airlines must allow name corrections free of cost up to 3 characters, provided the request is made within 24 hours of booking, for genuine typographical errors.
""" * 5
    },
    {
        "path": "iata/montreal_convention.md",
        "title": "Montreal Convention 1999 - Liability Rules",
        "authority": "IATA",
        "category": "iata",
        "content": """# Montreal Convention (MC99)

## Article 17 - Death and Injury of Passengers - Damage to Baggage
The carrier is liable for damage sustained in case of destruction or loss of, or of damage to, checked baggage upon condition only that the event which caused the destruction, loss or damage took place on board the aircraft or during any period within which the checked baggage was in the charge of the carrier.

## Article 19 - Delay
The carrier is liable for damage occasioned by delay in the carriage by air of passengers, baggage or cargo. 

## Article 22 - Limits of Liability
In the carriage of baggage, the liability of the carrier in the case of destruction, loss, damage or delay is limited to 1,288 Special Drawing Rights (SDR) for each passenger.

## Article 31 - Timely Notice of Complaints
In the case of damage, the person entitled to delivery must complain to the carrier forthwith after the discovery of the damage, and, at the latest, within seven days from the date of receipt in the case of checked baggage. In the case of delay, the complaint must be made at the latest within twenty-one days from the date on which the baggage has been placed at his or her disposal.
""" * 5
    },
    {
        "path": "airlines/indigo/conditions_of_carriage.md",
        "title": "IndiGo Conditions of Carriage",
        "authority": "IndiGo",
        "category": "airlines/indigo",
        "content": """# IndiGo Conditions of Carriage

## Article 8: Baggage
8.1 Free Baggage Allowance: Passengers are permitted free checked baggage allowance of 15 kg for domestic flights and cabin baggage of 7 kg.
8.2 Excess Baggage: Any baggage exceeding the free allowance will be charged an excess baggage fee at the prevailing rates per kg.
8.3 Valuable Items: IndiGo is not liable for loss or damage to fragile, perishable, or valuable items (including currency, jewelry, electronics, and documents) included in checked baggage.

## Article 10: Refunds
10.1 Voluntary Cancellations: If a passenger cancels a booking, cancellation fees apply as per the fare rules. The balance will be refunded.
10.2 Involuntary Cancellations (Airline's fault): If IndiGo cancels a flight, the passenger is entitled to a full refund to the original mode of payment or alternative travel arrangements without additional cost.
""" * 5
    },
    {
        "path": "airlines/air_india/baggage_policy.md",
        "title": "Air India Baggage Policy",
        "authority": "Air India",
        "category": "airlines/air_india",
        "content": """# Air India Baggage Guidelines

## Check-in Baggage
Domestic limits: Economy Class (20 kg - 25 kg depending on fare family), Business Class (35 kg).
International limits vary heavily by route (Weight Concept vs Piece Concept). For flights to North America, Economy class passengers are generally allowed 2 pieces of 23 kg each.

## Lost and Delayed Baggage
Passengers must file a Property Irregularity Report (PIR) at the arrival hall before leaving the airport. 
If baggage is delayed on a journey away from the home base, Air India will authorize a one-time interim relief (OPE) of INR 3000 for domestic travel and USD 50-100 for international travel to purchase essential items.
""" * 5
    }
]

def main():
    print(f"Generating Massive Datasets for Airlines Knowledge Base at {KNOWLEDGE_ROOT}")
    
    (KNOWLEDGE_ROOT / "metadata").mkdir(parents=True, exist_ok=True)
        
    for doc in LARGE_DOCUMENTS:
        filepath = KNOWLEDGE_ROOT / doc["path"]
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        filepath.write_text(doc["content"], encoding="utf-8")
        
        metadata = {
            "title": doc["title"],
            "authority": doc["authority"],
            "category": doc["category"],
            "document_type": "markdown",
            "domain": "airlines",
            "source_url": f"official://airlines/{doc['category']}/{filepath.name}"
        }
        
        meta_dir = KNOWLEDGE_ROOT / "metadata" / doc["category"]
        meta_dir.mkdir(parents=True, exist_ok=True)
        
        meta_path = meta_dir / f"{filepath.stem}.json"
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        
        print(f"Generated Airlines File: {filepath} ({len(doc['content'])} characters)")

if __name__ == "__main__":
    main()
