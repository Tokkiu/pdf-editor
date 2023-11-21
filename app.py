import itertools
import json
import os
import random
import pandas as pd
import streamlit as st
from PyPDF2.generic import NameObject
from openai import OpenAI
from pypdf import PdfReader, PdfWriter
from st_aggrid import AgGrid
import pypdfium2 as pdfium
import requests

st.set_page_config(page_title="FormUp",page_icon=':shark:')

# @st.cache_data
def load_docs(files):
    st.info("`Reading doc ...`")
    all_text = ""
    all_fields = []
    writers = []
    for file_path in files:
        file_extension = os.path.splitext(file_path.name)[1]
        if file_extension == ".pdf":
            # pdf_reader = PyPDF2.PdfReader(file_path)
            # pdf_reader.getFields()
            reader = PdfReader(file_path)
            writer = PdfWriter()

            if '/AcroForm' in reader.trailer['/Root'].keys():
                writer._root_object.update({NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]})

            fields = reader.get_fields()
            page = reader.pages[0]
            writer.add_page(page)
            all_fields.append(fields)
            writers.append(writer)
        else:
            st.warning('Please provide pdf.', icon="⚠️")
    return all_fields, writers




def main():
    
    foot = f"""
    <div style="
        position: fixed;
        bottom: 0;
        left: 30%;
        right: 0;
        width: 50%;
        padding: 0px 0px;
        text-align: center;
    ">
    </div>
    """

    st.markdown(foot, unsafe_allow_html=True)
    
    # Add custom CSS
    st.markdown(
        """
        <style>
        
        #MainMenu {visibility: hidden;
        # }
            footer {visibility: hidden;
            }
            .css-card {
                border-radius: 0px;
                padding: 30px 10px 10px 10px;
                background-color: #f8f9fa;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                margin-bottom: 10px;
                font-family: "IBM Plex Sans", sans-serif;
            }
            
            .card-tag {
                border-radius: 0px;
                padding: 1px 5px 1px 5px;
                margin-bottom: 10px;
                position: absolute;
                left: 0px;
                top: 0px;
                font-size: 0.6rem;
                font-family: "IBM Plex Sans", sans-serif;
                color: white;
                background-color: green;
                }
                
            .css-zt5igj {left:0;
            }
            
            span.css-10trblm {margin-left:0;
            }
            
            div.css-1kyxreq {margin-top: -40px;
            }
            
           
       
            
          

        </style>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.image("img/logo1.png")


   

    st.write(
    f"""
    <div style="display: flex; align-items: center; margin-left: 0;">
        <h1 style="display: inline-block;">FormUp</h1>
        <sup style="margin-left:5px;font-size:small; color: green;">beta</sup>
    </div>
    """,
    unsafe_allow_html=True,
        )
    
    


    
    
    st.sidebar.title("Menu")
    
    model_option = st.sidebar.radio(
        "Choose Models", ["gpt-4-1106-preview", "gpt-4"])

    global_info = st.sidebar.text_input(
        "Global Information")

    # os.environ['http_proxy'] = 'http://127.0.0.1:1087'
    # os.environ['https_proxy'] = 'http://127.0.0.1:1087'
    if "OPENAI_API_KEY" not in os.environ:
        openai_api_key = st.text_input(
            'Please enter your OpenAI API key or [get one here](https://platform.openai.com/account/api-keys)', value="", placeholder="Enter the OpenAI API key which begins with sk-")
        if openai_api_key:
            st.session_state.openai_api_key = openai_api_key
            os.environ["OPENAI_API_KEY"] = openai_api_key
        else:
            #warning_text = 'Please enter your OpenAI API key. Get yours from here: [link](https://platform.openai.com/account/api-keys)'
            #warning_html = f'<span>{warning_text}</span>'
            #st.markdown(warning_html, unsafe_allow_html=True)
            return
    else:
        openai_api_key = os.environ["OPENAI_API_KEY"]
        # os.environ["OPENAI_API_KEY"] = openai_api_key
        st.session_state.openai_api_key = openai_api_key

    uploaded_files = st.file_uploader("Upload a PDF Document", type=[
                                      "pdf"], accept_multiple_files=True)

    if uploaded_files:
        # Load and process the uploaded PDF or TXT files.
        pdf = uploaded_files[-1]
        loaded_fields, writers = load_docs(uploaded_files[-1:])
        if len(loaded_fields) != 1 or loaded_fields[0] is None:
            st.write(f"Document \"{pdf.name}\" uploaded but cannot be processed. Only fields preview is supported .")

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_api_key}"
            }


            from io import BytesIO
            import base64
            from io import BytesIO
            with BytesIO() as bytes_stream:
                writers[0].write(bytes_stream)
                page = pdfium.PdfDocument(bytes_stream.getvalue())[0]
                buffered = BytesIO()
                img = page.render(scale=4).to_pil()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

            payload = {
                "model": "gpt-4-vision-preview",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Pls summarize all fillable fields from this image of pdf file, and return them in JSON format. The JSON should only be organized in one level. Key is the field name. Value is the field type. Start output JSON with ### and end with ###. No comment in json response."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_str}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 300
            }

            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            data = response.json()['choices'][0]['message']['content']
            s = data.find('###')
            e = data.find('###', 1)
            if s == -1 or e == -1:
                st.write("Error to edit, pls try again")
            else:
                data = data[s + 3: e]
                print("Data", data)
                update_dic = json.loads(data)
                pd_dic = {"Field": [], "Type": [], "Option": []}
                for k, v in update_dic.items():
                    pd_dic["Field"].append(k)
                    pd_dic["Type"].append(v[0].upper() + v[1:] + " Box")
                    pd_dic["Option"].append("[TEXT]")
                AgGrid(pd.DataFrame(pd_dic))

            return
        else:
            st.write(f"Document \"{pdf.name}\" uploaded and processed. Pls enter as following fields:")

        state_dic = {}
        state_propmt_dic = {}
        fields = []
        for f, field in loaded_fields[0].items():
            fields.append(f)
            if '/_States_' in field:
                stats = []
                for s in field['/_States_']:
                    stats.append(s.replace('/', ''))
                state_dic[f] = field['/_States_']
                state_propmt_dic[f] = stats


        prompt_system = '''
        You are a poetic assistant, skilled in filling out information on pdf files. 
        To effectively fill in the information in the PDF file, you require a sentence of information to analyze and determine which details should be inputted into the designated text boxes.
        Fill all those text boxes and generate the appropriate output in JSON format.  
        Remember don't leave any box empty. If the information for one box wasn't given, please fill up that box with the most appropriate text according to your knowledge which should align with the information from the provided sentence.
        The key is the box name as input, the value is the information you just analyzed.
        The language of response should be same with provided sentence. Start output json with ### and end with ###. No comment in json response.
        '''

        prompt_user = '''
        Here is the list of text boxes you can fill up: [{}].
        Here is the global information you may need to know: "{}".
        Here is the sentence of input information you need: "{}".
        '''

        for f, stats in state_propmt_dic.items():
            prompt_user += "When filling up for '{}', you can choose from following options: [{}]\n".format(f, ",".join(
                stats))

        pd_dic = {"Field":[], "Type":[], "Option":[]}
        for f in fields:
            if f.lower().endswith("box"):
                fs = f.split(" ")
                pd_dic["Field"].append(" ".join(fs[:-2]))
                pd_dic["Type"].append(" ".join(fs[-2:]))

            elif len(f.split(".")) > 1:
                pd_dic["Field"].append(f.split(".")[-1])
                pd_dic["Type"].append("Text Box")

            else:
                pd_dic["Field"].append(f)
                pd_dic["Type"].append("Text Box")

            if f in state_propmt_dic:
                pd_dic["Option"].append(state_propmt_dic[f])
                if pd_dic["Type"][-1] == "Text Box":
                    pd_dic["Type"][-1] = "Check Box"
            else:
                pd_dic["Option"].append("[TEXT]")
        # st.write(pd.DataFrame(pd_dic))
        AgGrid(pd.DataFrame(pd_dic))

        field = ",".join(fields)
        writer = writers[0]

        user_information = st.text_input("Enter your information:")
        if user_information:
            prompt_user = prompt_user.format(field, global_info, user_information)
            client = OpenAI()
            completion = client.chat.completions.create(
                model=model_option,
                messages=[
                    {"role": "system", "content": prompt_system},
                    {"role": "user", "content": prompt_user}
                ]
            )
            data = completion.choices[0].message.content
            s = data.find('###')
            e = data.find('###', 1)
            if s == -1 or e == -1:
                st.write("Error to edit, pls try again")
            else:

                data = data[s + 3: e]
                update_dic = json.loads(data)


                for f in fields:
                    choose = update_dic[f]
                    if f in state_dic and choose not in state_dic[f]:
                        find = False
                        for state in state_dic[f]:
                            if state.lower().find(choose.lower()) != -1:
                                update_dic[f] = state
                                find = True
                        if not find:
                            update_dic.pop(f)


                writer.update_page_form_field_values(
                    writer.pages[0], update_dic
                )
                from io import BytesIO
                with BytesIO() as bytes_stream:
                    writer.write(bytes_stream)
                    import base64
                    b64data = base64.b64encode(bytes_stream.getvalue()).decode('utf-8')
                    # pdf_display = F'<embed src="data:application/pdf;base64,{b64data}" width="700" height="1000" type="application/pdf"></embed>'
                    # pdf_display = F'<iframe src="data:application/pdf;base64,{b64data}" width="700" height="1000" type="application/pdf"></iframe>'
                    # st.markdown(pdf_display, unsafe_allow_html=True)
                    # img = convert_from_bytes(bytes_stream.getvalue())[0]
                    page = pdfium.PdfDocument(bytes_stream.getvalue())[0]
                    img = page.render(scale=4).to_pil()

                    st.download_button(label="Download",
                                       data=bytes_stream.getvalue(),
                                       file_name="processed_" + pdf.name,
                                       mime='application/octet-stream')
                    st.image(img)




if __name__ == "__main__":
    main()
