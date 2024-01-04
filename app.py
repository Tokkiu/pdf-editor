import json
import os
import time

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
    # st.info("`Reading doc ...`")
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
            # print("hei", height, "w", width)
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

@st.cache_data(persist=True)
def FetchText(text):
    from openai import OpenAI
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        # response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a helpful assistant designed to summarize key points from given user's sentence."},
            {"role": "user", "content": text}
        ]
    )

    return response.choices[0].message.content

@st.cache_data(persist=True)
def FetchContent(img_str):
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

    prompt = '''
    Pls read the whole content and summarize the key ideas for me.
    Start output your summarization with ### and end with ###. No comment in response."
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
        # update_dic = json.loads(data)
        return data, None





def prompt_system():
    return '''
    You are a poetic assistant, skilled in filling out information on files. 
    To effectively fill in the information in the provided file, you require a sentence of information to analyze and determine which details should be inputted into the designated text boxes.
    Fill all those text boxes and generate the appropriate output in JSON format.  
    Remember don't leave any box empty. If the information for one box wasn't given, please fill up that box with the most appropriate text according to your knowledge which should align with the information from the provided sentence.
    The key is the box name as input, the value is the information you just analyzed.
    The language of response should be same with provided sentence. Start output json with ### and end with ###. No comment in json response.
    '''


st.session_state.key_id = 0


def addcell(pdf=None, url=None):
    # col1, col2 = st.columns(2)

    #
    # with col1:
    pdf_placeholder = st.empty()
    pdf = pdf_placeholder.file_uploader("", type=[
                              "pdf"], accept_multiple_files=False, key=st.session_state.key_id, label_visibility="collapsed")
    st.session_state.key_id += 1

    # with col2:
    url_placeholder = st.empty()
    url = url_placeholder.text_input('Write URL here',placeholder="Input URL here", label_visibility="collapsed", key=st.session_state.key_id)
    st.session_state.key_id += 1


    if pdf:
        pdf_placeholder.empty()
        url_placeholder.empty()
        return addpdf(pdf)

    if url:
        pdf_placeholder.empty()
        url_placeholder.empty()
        return addurl(url)

# from html2image import Html2Image
# hti = Html2Image()

@st.cache_data(persist=True)
def fetchURL(url):
    path = 'url_screen.png'
    hti.screenshot(url=url, save_as=path)
    with open(path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    update_dic, err = FetchContent(encoded_string)
    return update_dic, err

import requests
from bs4 import BeautifulSoup
import html2text

@st.cache_data(persist=True)
def FetchURLData(url):
    # url = 'https://github.com/ggerganov/llama.cpp/discussions/4167'
    response = requests.get(url)
    page = str(BeautifulSoup(response.content))
    h = html2text.HTML2Text()
    h.ignore_links = True
    return FetchText(h.handle(page)), None

def addurl(url):
    if not url.startswith("http"):
        st.write("Invalid URL format")

    update_dic, err = FetchURLData(url)
    # update_dic, err = fetchURL(url)
    if err is None:
        expander = st.expander(url, expanded=True)
        expander.write(update_dic)
        addcell()
    else:
        st.write("Error to preview: ", err)

@st.cache_data(persist=True, hash_funcs={st.runtime.uploaded_file_manager.UploadedFile: lambda pdf: pdf.name})
def FetchPDFData(pdf):
    loaded_fields, writers, readers, scale = load_docs([pdf])
    import base64
    from io import BytesIO
    with BytesIO() as bytes_stream:
        writers[0].write(bytes_stream)
        page = pdfium.PdfDocument(bytes_stream.getvalue())[0]
        buffered = BytesIO()
        img = page.render(scale=4).to_pil()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str

def addpdf(pdf=None):
    if pdf is None:
        pdf = st.file_uploader("", type=[
                                  "pdf"], accept_multiple_files=False, key=st.session_state.key_id, label_visibility="hidden")
        st.session_state.key_id += 1

    print("upload", pdf)
    # print("mode", st.session_state.mode)
    if pdf is None:
        return

    # with st.spinner('Wait for processing ' + pdf.name):
    img_str = FetchPDFData(pdf)
    update_dic, err = FetchContent(img_str)

    if err is None:
        # with st.container(border=True):
        #     st.write(update_dic)
        expander = st.expander(pdf.name, expanded=True)
        expander.write(update_dic)
        addcell()
    else:
        st.write("Error to preview: ", err)

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
        <h1 style="display: inline-block;">ShareUp</h1>
        <sup style="margin-left:5px;font-size:small; color: green;">beta</sup>
    </div>
    """,
    unsafe_allow_html=True,
        )
    
    


    
    
    st.sidebar.title("Menu")
    
    model_option = st.sidebar.radio(
        "Choose Models", ["gpt-4-vision-preview"])

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

    st.session_state.form_id = 0

    addcell()

    # while True:
    #     form = st.form(key='my-form'+str(st.session_state.form_id))
    #     st.session_state.form_id += 1
    #     pdf_placeholder = st.empty()
    #     url_placeholder = st.empty()
    #     txt_placeholder = st.empty()
    #     pdf = pdf_placeholder.file_uploader("", type=["pdf"], accept_multiple_files=False, key=st.session_state.key_id, label_visibility="collapsed")
    #     st.session_state.key_id += 1
    #     url = url_placeholder.text_input('Write URL here', placeholder="Input URL here", label_visibility="collapsed", key=st.session_state.key_id)
    #     st.session_state.key_id += 1
    #     submit = form.form_submit_button('Submit')
    #     while not submit:
    #         time.sleep(1)
    #     pdf_placeholder.empty()
    #     url_placeholder.empty()
    #     txt_placeholder.empty()
    #     addcell(pdf, url)


if __name__ == "__main__":
    main()
