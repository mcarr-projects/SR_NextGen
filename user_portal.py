import tkinter as tk
from tkinter import messagebox
from db_lib import add_card

def insert_question(question, answer, tags):
    added = add_card(question,answer,tags)
    if added:
        print('Card added.')

def add_card_launch():
    add_window = tk.Toplevel(root)
    add_window.title("Add Question")
    
    
    #question label/box

    qna_frame = tk.Frame(add_window)
    qna_frame.pack(side="top")
    
    q_frame = tk.Frame(qna_frame)
    q_frame.pack(side="left")
    q_label = tk.Label(q_frame, text="Question")
    q_label.pack(pady=(0,5))
    q_input = tk.Text(q_frame, width = 50, height = 15)
    q_input.pack(padx=5,pady=3)
    
    a_frame= tk.Frame(qna_frame)
    a_frame.pack(side="left")
    a_label = tk.Label(a_frame,text ="Answer")
    a_label.pack(pady=(0,5)) 
    a_input = tk.Text(a_frame, width = 50, height = 15)
    a_input.pack(padx=5,pady=3)
    
    
    bottom_frame = tk.Frame(add_window)
    bottom_frame.pack(side="bottom",pady=10)
    tag_label = tk.Label(bottom_frame, text = "Tags, comma sep")
    tag_label.pack(side= "left")
    tags_input = tk.Entry(bottom_frame, width = 70)
    tags_input.pack(side = "left")

    def add_handler():
        q_text = q_input.get("1.0", "end-1c").strip()  
        a_text = a_input.get("1.0", "end-1c").strip()
        tag_text = tags_input.get()
        insert_question(q_text, a_text, tag_text)

    add_button =tk.Button(bottom_frame, text="Add Question", command=add_handler)
    add_button.pack(side="left", padx=20)

    return 

root = tk.Tk()
root.title("Spaced Repition Practice")
root.geometry("300x100")

frame = tk.Frame(root)
frame.pack(expand=True)

add_card_btn = tk.Button(frame, text="Add Question", command=add_card_launch)
add_card_btn.pack(side="left", padx=5)

edit_card_btn = tk.Button(frame, text= "Edit Question")
edit_card_btn.pack(side = "left", padx=5)

review_card_btn = tk.Button(frame, text="Review Questions")
review_card_btn.pack(side = "left", padx=5)

root.mainloop()