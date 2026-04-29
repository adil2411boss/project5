import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent / "universities.db"

# University data with QS and THE rankings
UNIVERSITIES_DATA = [
    # USA
    ("Harvard University", "USA", "Cambridge, MA", 4, 5, "https://www.harvard.edu"),
    ("MIT", "USA", "Cambridge, MA", 2, 2, "https://www.mit.edu"),
    ("Stanford University", "USA", "Stanford, CA", 5, 4, "https://www.stanford.edu"),
    ("UC Berkeley", "USA", "Berkeley, CA", 60, 37, "https://www.berkeley.edu"),
    ("Yale University", "USA", "New Haven, CT", 14, 11, "https://www.yale.edu"),
    ("Princeton University", "USA", "Princeton, NJ", 8, 6, "https://www.princeton.edu"),
    ("Columbia University", "USA", "New York, NY", 54, 19, "https://www.columbia.edu"),
    ("University of Chicago", "USA", "Chicago, IL", 11, 13, "https://www.uchicago.edu"),
    ("Caltech", "USA", "Pasadena, CA", 6, 9, "https://www.caltech.edu"),
    ("Northwestern University", "USA", "Evanston, IL", 32, 23, "https://www.northwestern.edu"),
    
    # UK
    ("University of Oxford", "UK", "Oxford", 3, 1, "https://www.ox.ac.uk"),
    ("University of Cambridge", "UK", "Cambridge", 2, 3, "https://www.cam.ac.uk"),
    ("Imperial College London", "UK", "London", 6, 12, "https://www.imperial.ac.uk"),
    ("UCL", "UK", "London", 8, 16, "https://www.ucl.ac.uk"),
    ("London School of Economics", "UK", "London", 37, 27, "https://www.lse.ac.uk"),
    ("University of Edinburgh", "UK", "Edinburgh", 30, 30, "https://www.ed.ac.uk"),
    ("University of Manchester", "UK", "Manchester", 32, 54, "https://www.manchester.ac.uk"),
    ("University of Warwick", "UK", "Warwick", 78, 77, "https://www.warwick.ac.uk"),
    
    # Europe
    ("Swiss Federal Institute of Technology (ETH Zurich)", "Switzerland", "Zurich", 7, 31, "https://www.ethz.ch"),
    ("University of Zurich", "Switzerland", "Zurich", 62, 95, "https://www.uzh.ch"),
    ("Sorbonne University", "France", "Paris", 89, 73, "https://www.sorbonne-universite.fr"),
    ("University of Paris-Cité", "France", "Paris", 144, 78, "https://u-paris.fr"),
    ("Technische Universität München", "Germany", "Munich", 53, 34, "https://www.tum.de"),
    ("Heidelberg University", "Germany", "Heidelberg", 87, 74, "https://www.uni-heidelberg.de"),
    ("University of Amsterdam", "Netherlands", "Amsterdam", 57, 71, "https://www.uva.nl"),
    ("University of Copenhagen", "Denmark", "Copenhagen", 74, 84, "https://www.ku.dk"),
    ("Karolinska Institute", "Sweden", "Stockholm", 51, 43, "https://www.ki.se"),
    ("University of Oslo", "Norway", "Oslo", 70, 92, "https://www.uio.no"),
    
    # China
    ("Tsinghua University", "China", "Beijing", 25, 54, "https://www.tsinghua.edu.cn"),
    ("Peking University", "China", "Beijing", 41, 71, "https://english.pku.edu.cn"),
    ("Fudan University", "China", "Shanghai", 34, 101, "https://www.fudan.edu.cn"),
    ("Shanghai Jiao Tong University", "China", "Shanghai", 46, 97, "https://www.sjtu.edu.cn"),
    ("Zhejiang University", "China", "Hangzhou", 54, 117, "https://www.zju.edu.cn"),
    ("Nanjing University", "China", "Nanjing", 133, 150, "https://www.nju.edu.cn"),
    ("University of Science and Technology of China", "China", "Hefei", 137, 176, "https://en.ustc.edu.cn"),
    ("Xiamen University", "China", "Xiamen", 267, 301, "https://www.xmu.edu.cn"),
    
    # Canada
    ("University of Toronto", "Canada", "Toronto, ON", 26, 18, "https://www.utoronto.ca"),
    ("University of British Columbia", "Canada", "Vancouver, BC", 30, 25, "https://www.ubc.ca"),
    ("McMaster University", "Canada", "Hamilton, ON", 152, 201, "https://www.mcmaster.ca"),
    ("University of Alberta", "Canada", "Edmonton, AB", 110, 130, "https://www.ualberta.ca"),
    ("University of Montreal", "Canada", "Montreal, QC", 87, 140, "https://www.umontreal.ca"),
    ("Western University", "Canada", "London, ON", 194, 251, "https://www.uwo.ca"),
    ("University of Waterloo", "Canada", "Waterloo, ON", 72, 146, "https://www.uwaterloo.ca"),
    ("York University", "Canada", "Toronto, ON", 250, 301, "https://www.yorku.ca"),
]

def create_database():
    """Create and populate the universities database."""
    # Remove existing database if it exists
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing database at {DB_PATH}")
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create universities table
    cursor.execute("""
        CREATE TABLE universities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            qs_ranking INTEGER,
            the_ranking INTEGER,
            website_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert university data
    cursor.executemany("""
        INSERT INTO universities (name, country, city, qs_ranking, the_ranking, website_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, UNIVERSITIES_DATA)
    
    # Create an index on country for faster queries
    cursor.execute("CREATE INDEX idx_country ON universities(country)")
    
    # Commit changes
    conn.commit()
    
    # Display summary
    cursor.execute("SELECT COUNT(*) FROM universities")
    count = cursor.fetchone()[0]
    print(f"✅ Database created successfully at: {DB_PATH}")
    print(f"📊 Total universities added: {count}")
    
    # Show breakdown by country
    cursor.execute("""
        SELECT country, COUNT(*) as count 
        FROM universities 
        GROUP BY country 
        ORDER BY count DESC
    """)
    print("\n📍 Universities by country:")
    for country, country_count in cursor.fetchall():
        print(f"   {country}: {country_count}")
    
    conn.close()

if __name__ == "__main__":
    create_database()
