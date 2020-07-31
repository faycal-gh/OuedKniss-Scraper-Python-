import tkinter as tk
from tkinter import *
from tkinter import messagebox as mb
from tkinter import ttk
import requests #pip install requests
import sys # included
from config import * # pip install config
from bs4 import BeautifulSoup # pip install bs4
import sqlite3

def create_TreeView():
    global tv
    tv = ttk.Treeview(frm, columns=(1,2), show="headings", height="20")
    vsb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
    vsb.place(x=440, y=30, height=450)
    tv.configure(yscrollcommand=vsb.set)
    tv.pack()        
    tv.heading(1,text="Name")
    tv.heading(2,text="Price")

def clicked():
    try:
        get_number = number_entry.get()    
        get_phones(int(get_number))
    except:
        mb.showinfo(title='Warning',message="plz enter a number")
        
def clearAll():
    number_entry.delete(0, END)
    tv.delete(*tv.get_children())
    
def number_only(text):
    if str.isdigit(text) or text == '':
        return True
    else:
        return False

def connect():    
    global conn
    conn = sqlite3.connect('ouedkniss.db')
    global c
    c = conn.cursor()

def createTable():
    c.execute('''
    CREATE TABLE IF NOT EXISTS data(
        name varchar(255),
        price varchar(255)
    )''')

def dropTable():
    delete_query = "DROP TABLE data"
    c.execute(delete_query)
    
def insertData(name,price):
    connect()
    createTable()
    dropTable()
    createTable()
    inserting_query = "INSERT INTO data (name,price) VALUES ('" + name + "','" + price + "')"
    c.execute(inserting_query)


def get_response(url):
        try:
            response = requests.get(url)
        except requests.exceptions.RequestException as e:
            print(e)
            sys.exit(1)
        return response.content

def get_phones(number_of_phones):
    counter = 1    
    for i in range(1,203):
        r = get_response("https://www.ouedkniss.com/telephones/"+str(i))
        soup = BeautifulSoup(r , features="lxml") # pip install lxml
        annonce = soup.findAll('ul' , attrs={'class' : 'annonce_left'})
        print(f"======= page No: {i} =======")                        
        for elem in annonce:
                link = elem.find('a')['href']
                title = elem.find('h2')
                price = elem.find("span", itemprop="price")
                
                if title and price and link:
                    t = title.text.strip()
                    p = price.text.strip()
                    l = "https://www.ouedkniss.com/"+link                                        

                    insertData(t,p)
                    c.execute("SELECT * from data")
                    rows = c.fetchall()
                    for row in rows:
                        tv.insert('','end',values=row)
                                
                    conn.commit()
                    conn.close()                                               
                    counter += 1
                    if counter >= number_of_phones + 1:
                            break
        break

win = Tk()
frm = Frame(win)
frm.pack(side=tk.LEFT, padx=20)
create_TreeView()
reg_fun = frm.register(number_only)
global number_entry
number_entry = Entry(win, validate="key", validatecommand = (reg_fun,'%P') )
only_label = Label(text="Enter Numbers Only: ")
scrap_button = Button(text = "Scrap Now", command=clicked)
clear_button = Button(text="Clear All", command=lambda: clearAll())
number_entry.focus()
number_entry.place(x = 600, y = 50)
only_label.place(x = 480, y = 50)
scrap_button.place(x = 570, y = 100)
clear_button.place(x = 570,y = 150)
win.title("OuedKniss Scraper")
win.geometry('730x500')
win.resizable(False,False)
win.mainloop()
