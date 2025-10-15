from graph_db_interface import GraphDB

def add_incorrect_data(db: GraphDB):
    db.triple_add("https://www.sfb1574.kit.edu/ontologies/FlexConveyor#parcel2", "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#isPossessedBy", "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#module3")
   




def main():
    
    print("Strating")
    db = GraphDB("http://172.22.223.165:7200/", "admin", "qqq", "JMS_Usecase_2" )
    add_incorrect_data(db)

if __name__ == "__main__":
    main()