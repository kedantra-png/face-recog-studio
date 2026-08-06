# -*- coding: utf-8 -*-
"""
Inspect & Hash Studio Passkeys in Local MongoDB
"""
import asyncio
import os
import time
import hashlib
from motor.motor_asyncio import AsyncIOMotorClient

def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return key.hex(), salt.hex()

def verify_password_hash(password: str, stored_hash: str, stored_salt: str) -> bool:
    try:
        salt = bytes.fromhex(stored_salt)
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return key.hex() == stored_hash
    except Exception:
        return False

async def inspect_studios():
    db_url = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DATABASE_NAME", "face_recog_db_v2")
    
    print(f"Connecting to MongoDB at {db_url} -> Database: {db_name}")
    client = AsyncIOMotorClient(db_url)
    db = client[db_name]

    studios = await db.studios.find({}).to_list(100)
    print(f"\nFound {len(studios)} studio account(s) in MongoDB 'studios' collection:")

    for idx, s in enumerate(studios, 1):
        s_id = s.get("studio_id")
        s_name = s.get("studio_name")
        p_hash = s.get("passkey_hash", "N/A")
        salt = s.get("salt", "N/A")
        is_active = s.get("is_active", True)
        print(f"[{idx}] ID: {s_id} | Name: '{s_name}' | Active: {is_active}")
        print(f"    Passkey Hash: {p_hash[:16]}... | Salt: {salt[:16]}...")

    # If no studios or missing chaya_studio, seed Chaya Studio with PBKDF2-HMAC hashed passkey
    chaya_doc = await db.studios.find_one({"$or": [{"studio_id": "chaya_studio"}, {"studio_name": "Chaya Studio"}]})
    if not chaya_doc:
        print("\nSeeding 'Chaya Studio' with PBKDF2-HMAC hashed passkey ('chaya@2005')...")
        passkey_h, salt_h = hash_password("chaya@2005")
        now = time.time()
        chaya_doc = {
            "studio_id": "chaya_studio",
            "studio_name": "Chaya Studio",
            "passkey_hash": passkey_h,
            "salt": salt_h,
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        await db.studios.insert_one(chaya_doc)
        print("Successfully created 'Chaya Studio' in local MongoDB!")
    else:
        # Verify passkey_hash for chaya@2005
        p_hash = chaya_doc.get("passkey_hash", "")
        salt = chaya_doc.get("salt", "")
        if p_hash and salt:
            valid = verify_password_hash("chaya@2005", p_hash, salt)
            print(f"\nPBKDF2 Hash Verification for 'chaya@2005' against DB record: {'MATCHED' if valid else 'FAILED'}")
            if not valid:
                print("Updating 'Chaya Studio' passkey_hash to fresh PBKDF2 hash...")
                passkey_h, salt_h = hash_password("chaya@2005")
                await db.studios.update_one(
                    {"_id": chaya_doc["_id"]},
                    {"$set": {"passkey_hash": passkey_h, "salt": salt_h, "updated_at": time.time()}}
                )
                print("Successfully updated PBKDF2 passkey hash!")
        else:
            print("Ensuring PBKDF2 passkey_hash and salt exist on Chaya Studio...")
            passkey_h, salt_h = hash_password("chaya@2005")
            await db.studios.update_one(
                {"_id": chaya_doc["_id"]},
                {"$set": {"passkey_hash": passkey_h, "salt": salt_h, "updated_at": time.time()}}
            )
            print("Successfully saved PBKDF2 hash!")

    # Print final collection status
    print("\n--- FINAL MONGODB STUDIOS COLLECTION SUMMARY ---")
    final_studios = await db.studios.find({}).to_list(100)
    for s in final_studios:
        print(f"Studio ID: {s.get('studio_id')} | Name: '{s.get('studio_name')}' | Passkey PBKDF2 Hashed: {bool(s.get('passkey_hash'))}")

if __name__ == "__main__":
    asyncio.run(inspect_studios())
