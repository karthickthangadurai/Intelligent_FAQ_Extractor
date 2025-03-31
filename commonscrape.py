"""
FAQ Extraction Application

This module extracts FAQs from various websites, segregates them by organization,
and stores them in a structured format. Supports both single URL and multiple URLs.
"""

import json
import logging
import os
import re
import time
from typing import Dict, List, Optional, Any, Tuple, Union

import pandas as pd
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from langchain_community.document_loaders import FireCrawlLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("faq_extraction.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FAQExtractor:
    """
    A class to extract FAQs from websites and organize them by organization.
    """

    def __init__(self, firecrawl_api_key: str, google_api_key: str):
        """
        Initialize the FAQ extractor with necessary API keys.

        Args:
            firecrawl_api_key: API key for FireCrawl service
            google_api_key: API key for Google Generative AI
        """
        self.app = FirecrawlApp(api_key=firecrawl_api_key)
        self.llm = self._initialize_llm(google_api_key)
        self.data_dict = self._initialize_data_dict()
        self.notcollected = []

    @staticmethod
    def _initialize_data_dict() -> Dict[str, List]:
        """
        Initialize the data dictionary with empty lists for each field.

        Returns:
            Dictionary with empty lists for each field
        """
        return {
            'organisation_name': [],
            'category': [],
            'question': [],
            'answer': [],
            'links': [],
            'URL': []
        }

    @staticmethod
    def _initialize_llm(api_key: str) -> ChatGoogleGenerativeAI:
        """
        Initialize the language model with the provided API key.

        Args:
            api_key: Google Generative AI API key

        Returns:
            Configured LLM instance
        """
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-thinking-exp",
            temperature=0,
            max_tokens=None,
            timeout=120,  # Adding timeout to prevent hanging
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True
    )
    def _crawl_website(self, url: str) -> Optional[str]:
        """
        Crawl a website and extract its content.

        Args:
            url: Website URL to crawl

        Returns:
            Extracted markdown content or None if extraction failed
        """
        try:
            crawl_result = self.app.crawl_url(
                url,
                params={
                    'limit': 1,
                    'scrapeOptions': {
                        'formats': ['markdown'],
                        'actions': [{"type": "wait", "milliseconds": 10000}]
                    }
                }
            )
            print(crawl_result)
            return crawl_result['data'][0]['markdown']
        except Exception as e:
            logger.error(f"Failed to crawl {url}: {str(e)}")
            self.notcollected.append(url)
            time.sleep(30)
            return None

    def _create_extraction_template(self, context: str) -> str:
        """
        Create the prompt template for FAQ extraction.

        Args:
            context: Website content in markdown format

        Returns:
            Formatted prompt template
        """
        return f"""
        Task:

        Extract frequently asked questions (FAQs) from the given markdown or context.
        Read the markdown document from starting to end. Identify the question and you will get the answer.
        Extract each question and entire answer for the same question.
        DO NOT include "Related Articles" sections or links to other FAQ questions in the extracted answer.
        Identify and structure the data in JSON format with the following fields:

        Expected output:

        organisation_name: The name of the university or organization.
        category: The category the FAQs belong to.
        question: The FAQ question.
        answer: A concise response extracted from the markdown or context.
        links (if available): Any hyperlinks related to the FAQ, including the display text and URL only if available.
        
        Ensure the extracted text remains accurate and preserves key details. If links are embedded within the answer, extract them separately in a structured format. Ignore or exclude any links that point to other FAQ questions or that appear in "Related Articles" sections.

        Examples:
        Example 1: Extracting FAQs
        Input:

        What financial aid is available?
        Watch our financial aid overview video here to learn about which financial aid services we offer, how much tuition costs, and how to make college affordable.

        Expected Output:

        {{
          "question": "What financial aid is available?",
          "answer": "Watch our financial aid overview video to learn about which financial aid services we offer, how much tuition costs, and how to make college affordable.",
          "links": [
            {{
              "text": "Financial Aid Overview Video",
              "url": "https://www.nu.edu/admissions/financial-aid-and-scholarships/"
            }}
          ]
        }}

        context:["placeholder","{context}"]\n
        """

    def _extract_json_from_response(self, response_content: str) -> Dict[str, Any]:
        """
        Extract JSON object from LLM response.

        Args:
            response_content: LLM response content

        Returns:
            Extracted JSON object
        """
        try:
            json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
            matches = re.findall(json_pattern, response_content, re.DOTALL)
            if not matches:
                raise ValueError("No JSON object found in the response")
            return matches
        except:
            logger.error("Failed to extract JSON from LLM response")
            return {}

    def _process_faq_data(self, json_obj: Dict[str, Any], url: str) -> None:
        """
        Process and store the extracted FAQ data.

        Args:
            json_obj: Extracted FAQ data
            url: Source URL
        """
        for field in ['organisation_name', 'category', 'question', 'answer', 'links']:
            if field not in json_obj:
                json_obj[field] = "Not available"
        
        self.data_dict["organisation_name"].append(json_obj['organisation_name'])
        self.data_dict["category"].append(json_obj['category'])
        self.data_dict["question"].append(json_obj['question'])
        self.data_dict["answer"].append(json_obj['answer'])
        self.data_dict["links"].append(json_obj['links'])
        self.data_dict['URL'].append(url)

    def process_single_url(self, url: str) -> Dict[str, Any]:
        """
        Process a single URL and extract FAQs.

        Args:
            url: URL to process

        Returns:
            Dictionary containing extracted FAQ data for this URL
        """
        logger.info(f"Processing single URL: {url}")
        
        # Skip if URL already processed
        if url in self.data_dict['URL']:
            logger.info(f"URL already processed: {url}")
            return self._get_url_data(url)
        
        try:
            # Crawl website
            context = self._crawl_website(url)
            if not context:
                logger.warning(f"No content extracted from {url}")
                return {}
            
            # Create extraction template
            template = self._create_extraction_template(context)
            
            # Extract FAQs using LLM
            answer = self.llm.invoke(template)
            
            # Parse response
            json_obj = self._extract_json_from_response(answer.content)
            #print(json_obj)
            # Process and store data
            for jsondict in json_obj:
                try: 
                    self._process_faq_data(json.loads(jsondict), url)
                    pass
                except (json.JSONDecodeError, IndexError) as e:
                    logger.error(f"Failed to parse JSON from response: {str(e)}")
                    raise
            
            
            logger.info(f"Successfully extracted FAQ from {url}")
            
            return self._get_url_data(url)
            
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return {}

    def _get_url_data(self, url: str) -> Dict[str, Any]:
        """
        Get the data for a specific URL from the data dictionary.

        Args:
            url: URL to retrieve data for

        Returns:
            Dictionary containing the data for the specified URL
        """
        if url not in self.data_dict['URL']:
            return {}
        
        idx = self.data_dict['URL'].index(url)
        return {
            'organisation_name': self.data_dict['organisation_name'][idx],
            'category': self.data_dict['category'][idx],
            'question': self.data_dict['question'][idx],
            'answer': self.data_dict['answer'][idx],
            'links': self.data_dict['links'][idx],
            'URL': url
        }

    def extract_faqs(self, urls: Union[str, List[str]], max_urls: Optional[int] = None) -> Dict[str, List]:
        """
        Extract FAQs from a single URL or multiple URLs.

        Args:
            urls: Single URL string or list of URLs to process
            max_urls: Maximum number of URLs to process (optional, only applies to list input)

        Returns:
            Dictionary containing extracted FAQ data
        """
        # Handle single URL case
        if isinstance(urls, str):
            self.process_single_url(urls)
            return self.data_dict
        
        # Handle list of URLs case
        if max_urls:
            urls = urls[:max_urls]
        
        total_urls = len(urls)
        for i, url in enumerate(urls):
            logger.info(f"Processing URL {i+1}/{total_urls}: {url}")
            self.process_single_url(url)
        
        return self.data_dict

    def save_to_csv(self, filename: str = "extracted_duplicate_links23.csv") -> None:
        """
        Save the extracted FAQ data to a CSV file.

        Args:
            filename: Name of the output CSV file
        """
        try:
            df = pd.DataFrame(self.data_dict)
            df.to_csv(filename, index=False,encoding = 'utf-8-sig')
            logger.info(f"FAQ data saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save data to CSV: {str(e)}")


def load_environment_variables() -> Tuple[str, str]:
    """
    Load environment variables from .env file.

    Returns:
        Tuple containing FireCrawl API key and Google API key
    """
    load_dotenv()
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    google_api_key = os.getenv("GOOGLE_API_KEY")
    
    if not firecrawl_api_key:
        raise ValueError("FIRECRAWL_API_KEY environment variable is not set")
    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set")
    
    return firecrawl_api_key, google_api_key


def main():
    """
    Main function to run the FAQ extraction process.
    """
    try:
        # Load API keys from environment variables
        firecrawl_api_key, google_api_key = load_environment_variables()
        
        # Initialize FAQ extractor
        extractor = FAQExtractor(firecrawl_api_key, google_api_key)
        
        # Example of handling both input types
        try:
            # First try to read URLs from a CSV file
            df = pd.read_csv(r"E:\All_Folder\VS_Code\Scrapping_project\plattslinks - Copy.csv")
            urls = df["Links"].tolist()
            logger.info(f"Found {len(urls)} URLs in input CSV file")
        except Exception as e:
            logger.warning(f"Could not read URLs from CSV: {str(e)}")
            logger.info("Checking for single URL in environment variables")
            # Fall back to single URL from environment variable
            single_url = "https://platts.my.site.com/CIKnowledgeBase/s/article/How-do-I-reset-my-password-for-S-P-Global-Commodity-Insights-website"

            if single_url:
                urls = single_url
                logger.info(f"Processing single URL from environment: {single_url}")
            else:
                logger.error("No URLs found in CSV or environment variables")
                raise ValueError("No URLs provided for processing")
        
        # Extract FAQs (works with both string and list inputs)
        extracted_data = extractor.extract_faqs(urls, max_urls=None)
        

        # Save results
        extractor.save_to_csv()
        
        if isinstance(urls, str):
            logger.info(f"FAQ extraction completed for single URL: {urls}")
        else:
            logger.info(f"FAQ extraction completed. Processed {len(extracted_data['URL'])} URLs.")
        
    except Exception as e:
        logger.critical(f"Critical error in main function: {str(e)}")
        raise


if __name__ == "__main__":
    main()
