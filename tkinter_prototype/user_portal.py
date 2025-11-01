import tkinter as tk
from tkinter import messagebox
from db_lib import add_card, get_cards

def insert_question(question, answer, tags):
    added = add_card(question,answer,tags)
    if added.get("success"):
        print('Card added.')
    else:
        print("Error:", added.get("error"))

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
    q_input = tk.Text(q_frame, width = 50, height = 15, wrap="word")
    q_input.pack(padx=5,pady=3)
    
    a_frame= tk.Frame(qna_frame)
    a_frame.pack(side="left")
    a_label = tk.Label(a_frame,text ="Answer")
    a_label.pack(pady=(0,5)) 
    a_input = tk.Text(a_frame, width = 50, height = 15, wrap = "word")
    a_input.pack(padx=5,pady=3)
    
    #tags input and add button    
    bottom_frame = tk.Frame(add_window)
    bottom_frame.pack(side="bottom",pady=10)
    tag_label = tk.Label(bottom_frame, text = "Tags, comma sep")
    tag_label.pack(side= "left")
    tags_input = tk.Entry(bottom_frame, width = 70)
    tags_input.pack(side = "left")

    def add_handler():
        q_text = q_input.get("1.0", "end-1c").strip()  
        a_text = a_input.get("1.0", "end-1c").strip()
        tag_text = [t.strip() for t in tags_input.get().split(',') if t.strip()]
        insert_question(q_text, a_text, tag_text)

    add_button =tk.Button(bottom_frame, text="Add Question", command=add_handler)
    add_button.pack(side="left", padx=20)

    return 

def launch_review_menu():
    add_window = tk.Toplevel(root)
    add_window.title("Review Menu")
    
    review_all_btn = tk.Button(add_window, text = "Review All", command = card_review)
    review_all_btn.pack(padx=10,pady=10)

def card_review():
    add_window = tk.Toplevel(root)
    add_window.title("Review Questions")
    add_window.geometry("1200x600")
        
    #question label/box
    qna_frame = tk.Frame(add_window)
    qna_frame.pack(side="top")
    
    q_frame = tk.Frame(qna_frame)
    q_frame.pack(side="left")
    q_label = tk.Label(q_frame, text="Question")
    q_label.pack(pady=(0,5))
    q_input = tk.Text(q_frame, width = 70, height = 30)
    q_input.pack(padx=5,pady=3)
    
    a_frame= tk.Frame(qna_frame)
    a_frame.pack(side="left")
    a_label = tk.Label(a_frame,text ="Answer")
    a_label.pack(pady=(0,5)) 
    a_input = tk.Text(a_frame, width = 70, height = 30)
    a_input.pack(padx=5,pady=3)

    bottom_frame = tk.Frame(add_window)
    bottom_frame.pack(side="bottom",pady=10)
    
    
    to_review =  get_cards()
    curr_index = tk.IntVar(value=0)

    if not to_review:
        messagebox.showinfo("No questions available", "No questions came up for your selected tags.")
        add_window.destroy()
        return
    answer_shown = tk.BooleanVar(value=False)

    def show_question():
        question = to_review[curr_index.get()]['question']
        
        q_input.config(state="normal")
        q_input.delete("1.0","end")
        q_input.insert("1.0", question)
        q_input.config(state='disabled')
        
        a_input.config(state="normal")
        a_input.delete("1.0","end")
        answer_shown.set(False)

    def reveal_answer():
        if answer_shown.get():
            return
        answer = to_review[curr_index.get()]['answer']
        current_text = a_input.get("1.0","end").strip()
        
        a_input.config(state = "normal")
        a_input.delete("1.0", "end")
        a_input.insert("1.0", f"Your Answer:\n{current_text}\n\n")
        a_input.insert("end",f"Suggested Answer:\n{answer}\n\n")
        a_input.insert("end",f"Evaluation:\n(Under construction)")
        
        a_input.config(state = "disabled")
        answer_shown.set(True)

    def next_card():
        idx = curr_index.get() + 1
        if idx >= len(to_review):
            messagebox.showinfo("Done","All cards reviewed!")
            add_window.destroy()
            return
        curr_index.set(idx)
        show_question()
    
    show_ans_btn = tk.Button(bottom_frame, text = "Show Answer", command = reveal_answer)
    show_ans_btn.pack(side="left",padx=10)

    next_q_btn = tk.Button(bottom_frame, text = "Next", command = next_card)
    next_q_btn.pack(side="left",padx=10)

    show_question()

def edit_card_launch():
    edit_window = tk.Toplevel(root)
    edit_window.title("Edit Questions")
    edit_window.geometry("1200x600")

    main_frame = tk.Frame(edit_window)
    main_frame.pack(fill="both", expand = True)

    list_frame = tk.Frame(main_frame)
    list_frame.pack(side="left", fill="y", padx=10,pady=10)

    tk.Label(list_frame, text="Questions").pack()
    q_list = tk.Listbox(list_frame, width = 40, height = 30)
    q_list.pack(fill="y",expand=True)

    editor_frame = tk.Frame(main_frame)
    editor_frame.pack(side="left",fill="both",expand=True, padx=10,pady=10)

    tk.Label(editor_frame, text="Question").pack(anchor='w')
    q_input = tk.Text(editor_frame, width = 70, height=10, wrap="word")
    q_input.pack(fill="x",pady=5)
    
    tk.Label(editor_frame, text = "Answer").pack(anchor="w")
    a_input = tk.Text(editor_frame, width= 70, height = 10, wrap="word")
    a_input.pack(fill="x",pady=5)

    tk.Label(editor_frame, text="Tags (comma-separated)").pack(anchor="w")
    tags_input = tk.Entry(editor_frame, width=70)
    tags_input.pack(fill="x", pady=5)

    all_cards = get_cards()
    to_review = all_cards

    def save_changes():
        #ToDo
        return 
    
    save_btn = tk.Button(editor_frame, text="Save Changes", command=save_changes)
    save_btn.pack(pady=5)

    def refresh_list():
        q_list.delete(0,"end")
        for card in to_review:
            preview = " ".join(card["question"].split()[:3])
            q_list.insert("end",f"{card["id"]} | {preview}...")
    
    def on_select(event):
        selection = q_list.curselection()
        if not selection:
            return
        card = to_review[selection[0]]

        
        print(selection)
        print(selection[0])
        print(card)

        q_input.delete("1.0","end")
        q_input.insert("1.0", card["question"])

        a_input.delete("1.0","end")
        a_input.insert("1.0",card["answer"])

        tags_input.delete(0,"end")
        tags_input.insert(0,", ".join(card["tags"]))


    q_list.bind("<<ListboxSelect>>", on_select)
    refresh_list()

root = tk.Tk()
root.title("Spaced Repition Practice")
root.geometry("300x100")

frame = tk.Frame(root)
frame.pack(expand=True)

add_card_btn = tk.Button(frame, text="Add Question", command=add_card_launch)
add_card_btn.pack(side="left", padx=5)

edit_card_btn = tk.Button(frame, text= "Edit Questions", command = edit_card_launch)
edit_card_btn.pack(side = "left", padx=5)

review_card_btn = tk.Button(frame, text="Review Questions", command=launch_review_menu)
review_card_btn.pack(side = "left", padx=5)

root.mainloop()