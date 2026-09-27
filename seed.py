from database import init_db, clear_all_data, clean_upload_folders, seed_db

if __name__ == '__main__':
    print("Executing Mentora AI Complete Data Reset & Clean Seeding...")
    init_db()
    clear_all_data()
    clean_upload_folders()
    seed_db()
    print("Mentora AI fresh initialization completed successfully.")

