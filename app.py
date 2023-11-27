import json
import os
import pandas as pd
import streamlit as st
from PyPDF2.generic import NameObject
from openai import OpenAI
from pypdf import PdfReader, PdfWriter
from st_aggrid import AgGrid
import pypdfium2 as pdfium
import requests
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import base64
from io import BytesIO

st.set_page_config(page_title="FormUp",page_icon=':shark:')

# @st.cache_data
def load_docs(files):
    st.info("`Reading doc ...`")
    all_text = ""
    all_fields = []
    writers = []
    readers = []
    scale = []
    for file_path in files:
        file_extension = os.path.splitext(file_path.name)[1]
        if file_extension == ".pdf":
            reader = PdfReader(file_path)
            page = reader.pages[0]

            # pdfrwpages = pdfrwReader(file_path).pages
            # pdfrwpg = pagexobj(pdfrwpages[0])
            if page.get('/Rotate', 0) in [90, 270]:
                print('转90-270')
                height, width = page['/MediaBox'][2] - page['/MediaBox'][0], page['/MediaBox'][3] - page['/MediaBox'][1]
            else:
                height, width = page['/MediaBox'][3] - page['/MediaBox'][1], page['/MediaBox'][2] - page['/MediaBox'][0]
            print("hei", height, "w", width)
            # width, height = pdfrwpg.BBox[2], pdfrwpg.BBox[3]
            scale = [width, height]
            writer = PdfWriter()

            if '/AcroForm' in reader.trailer['/Root'].keys():
                writer._root_object.update({NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]})

            fields = reader.get_fields()
            writer.add_page(page)
            all_fields.append(fields)
            writers.append(writer)
            readers.append(reader)
        else:
            st.warning('Please provide pdf.', icon="⚠️")
    return all_fields, writers, readers, scale


def writePdf(existing_pdf, text, position, scale):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    for k, v in text.items():
        pos = position[k]
        print(scale, "K [", k, "]  v [" , v, "] pos", pos)
        can.drawString(int(pos[0]) * scale, int(pos[1]) * scale, v)

    can.save()

    # move to the beginning of the StringIO buffer
    packet.seek(0)

    # create a new PDF with Reportlab
    new_pdf = PdfReader(packet)
    # read your existing PDF
    # existing_pdf = PdfReader(open("/Users/ary/Downloads/ust.pdf", "rb"))
    output = PdfWriter()
    # add the "watermark" (which is the new pdf) on the existing page
    page = existing_pdf.pages[0]
    page.merge_page(new_pdf.pages[0])
    output.add_page(page)
    # finally, write "output" to a real file
    # output_stream = open("/Users/ary/Downloads/ust.destination.pdf", "wb")
    # output_stream.close()
    with BytesIO() as bytes_stream:
        output.write(bytes_stream)
        return bytes_stream.getvalue()



def askPosition(img_str):
    # OpenAI API Key
    api_key = os.environ['OPENAI_API_KEY']

    # Function to encode the image
    def encode_image(image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    # Path to your image

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    prompt = '''
    Pls give me the exact position of all fillable blank from this image, and return them in JSON format.
    The key of json is the blank name and the value is json is the blank information. 
    The JSON should only be organized in one level. 
    More precisely, the value is a list.
    The first element of this list is blank type.
    The second element of this list is the relative position in the pixel of the blank. 

    Here we assume the left and bottom should be start point. 
    Additionally, the key of 'RAWSCALE' should be put in this json. The value of 'RAWSCALE' is the pixel width and height of this image. 
    Start output JSON with ### and end with ###. No comment in json response."
    '''

    payload = {
        "model": "gpt-4-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
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
        "max_tokens": 1000
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    data = response.json()['choices'][0]['message']['content']
    s = data.find('###')
    e = data.find('###', 1)
    if s == -1 or e == -1:
        return {}, data
    else:
        data = data[s + 3: e]
        update_dic = json.loads(data)
        return update_dic, None





def prompt_system():
    return '''
    You are a poetic assistant, skilled in filling out information on files. 
    To effectively fill in the information in the provided file, you require a sentence of information to analyze and determine which details should be inputted into the designated text boxes.
    Fill all those text boxes and generate the appropriate output in JSON format.  
    Remember don't leave any box empty. If the information for one box wasn't given, please fill up that box with the most appropriate text according to your knowledge which should align with the information from the provided sentence.
    The key is the box name as input, the value is the information you just analyzed.
    The language of response should be same with provided sentence. Start output json with ### and end with ###. No comment in json response.
    '''

def prompt_user():
    return '''
    Here is the list of text boxes you can fill up: [{}].
    Here is the global information you may need to know: "{}".
    Here is the sentence of input information you need: "{}".
    '''


def ask_user_info(model_option, global_info, user_information, field, my_prompt_user):
    my_prompt_user = my_prompt_user.format(field, global_info, user_information)
    client = OpenAI()
    completion = client.chat.completions.create(
        model=model_option,
        messages=[
            {"role": "system", "content": prompt_system()},
            {"role": "user", "content": my_prompt_user}
        ]
    )
    data = completion.choices[0].message.content
    s = data.find('###')
    e = data.find('###', 1)
    if s == -1 or e == -1:
        return {}
    else:
        print("User info", data)
        data = data[s + 3: e]
        update_dic = json.loads(data)
        return update_dic

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

    if 'mode' not in st.session_state:
        st.session_state['mode'] = 'upload'

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


    filePath = {
        "Payroll Register":"Payroll_Register_Template.pdf",
        "OoPdfFormExample":"OoPdfFormExample.pdf",
        "Donation gift card":"donation_gift_card.pdf",
    }


    col1, col2 = st.columns([3,1])

    with col1:
        def changepdf():
            st.session_state.mode = "upload"

        uploaded_files = st.file_uploader("Upload a PDF Document", type=[
                                      "pdf"], accept_multiple_files=False, on_change=changepdf)
    with col2:

        def changevalue():
            st.session_state.mode = "sample"

        selected_file = st.selectbox(
            "Choose from samples",
            filePath.keys(),
            index=None,
            placeholder="Pick one pdf ...",
            on_change=changevalue
        )



    print("upload", uploaded_files)
    print("sample", selected_file)
    if st.session_state.mode == "upload":
        pdf = uploaded_files
    else:

        pdf = open(filePath[selected_file], 'rb')
    # print("mode", st.session_state.mode)
    if pdf:
        loaded_fields, writers, readers, scale = load_docs([pdf])
        if st.session_state.mode == "sample":

            # preader = readers[0]
            st.write("You select sample pdf file:")
            preader = PdfReader(filePath[selected_file])
            pwriter = PdfWriter()
            pwriter.add_page(preader.pages[0])
            from io import BytesIO
            with BytesIO() as bytes_stream:
                pwriter.write(bytes_stream)
                page = pdfium.PdfDocument(bytes_stream.getvalue())[0]
                img = page.render(scale=4).to_pil()
                st.image(img, caption=pdf.name)



        if len(loaded_fields) != 1 or loaded_fields[0] is None:
            st.write(f"Document \"{pdf.name}\" uploaded but cannot be processed. Try to use ChatGPT to locate fields.")

            import base64
            from io import BytesIO
            with BytesIO() as bytes_stream:
                writers[0].write(bytes_stream)
                page = pdfium.PdfDocument(bytes_stream.getvalue())[0]
                buffered = BytesIO()
                img = page.render(scale=4).to_pil()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

            update_dic, err = askPosition(img_str)
            if err is None:

                pd_dic = {"Field": [], "Type": [], "Option": []}
                fields = []
                pos_dic = {}
                raww = update_dic["RAWSCALE"] if "RAWSCALE" in update_dic else [1086, 768]
                # print("update", update_dic)
                for k, v_arr in update_dic.items():
                    if k == "RAWSCALE":
                        continue

                    fields.append(k)
                    print("k", k, "v", v_arr)
                    v = v_arr[0]
                    pos = v_arr[1][-2:]
                    pos_dic[k] = pos
                    pd_dic["Field"].append(k)
                    pd_dic["Type"].append(v[0].upper() + v[1:] + " Box")
                    pd_dic["Option"].append("[TEXT]")
                AgGrid(pd.DataFrame(pd_dic))


                field = ",".join(fields)
                user_information = st.text_input("Enter your information:")
                if user_information:
                    my_prompt_user = prompt_user().format(field, global_info, user_information)
                    info_dic = ask_user_info(model_option, global_info, user_information, field, my_prompt_user)
                    if len(info_dic) > 1:
                        reader = readers[0]
                        sizescale = int(min(scale))/int(min(raww))
                        # print("scale", sizescale, raww, scale)
                        pdfdata = writePdf(reader, info_dic, pos_dic, sizescale)
                        page = pdfium.PdfDocument(pdfdata)[0]
                        img = page.render(scale=4).to_pil()
                        st.download_button(label="Download",
                                           data=pdfdata,
                                           file_name="processed_" + pdf.name,
                                           mime='application/octet-stream')
                        st.image(img)
            else:
                st.write("Error to preview:", err)

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

            my_prompt_user = prompt_user()
            for f, stats in state_propmt_dic.items():
                 my_prompt_user += "When filling up for '{}', you can choose from following options: [{}]\n".format(f, ",".join(
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

            writer = writers[0]

            field = ",".join(fields)
            user_information = st.text_input("Enter your information:")
            if user_information:
                update_dic = ask_user_info(model_option, global_info, user_information, field, my_prompt_user)
                if len(update_dic) > 1:
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
                        filled = bytes_stream.getvalue()
                        page = pdfium.PdfDocument(filled)[0]
                        img = page.render(scale=4).to_pil()
                        st.download_button(label="Download",
                                           data=filled,
                                           file_name="processed_" + pdf.name,
                                           mime='application/octet-stream')
                        st.image(img, caption="filled_" + pdf.name)
                else:
                    st.write("Error to edit, pls try again")


if __name__ == "__main__":
    main()
