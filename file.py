import os
import re
import json
import logging
from typing import Dict, List, Optional, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("faq_extractor")

class FAQExtractor:
    """Class to extract FAQs from websites using Firecrawl and LLM processing."""
    
    def __init__(self, firecrawl_api_key: str, google_api_key: str):
        """
        Initialize the FAQ extractor with API keys.
        
        Args:
            firecrawl_api_key: API key for FirecrawlApp
            google_api_key: API key for Google Generative AI
        """
        self.firecrawl_api_key = firecrawl_api_key
        self.google_api_key = google_api_key
        self._setup_llm()
        
    def _setup_llm(self) -> None:
        """Set up the LLM with Google Generative AI."""
        try:
            os.environ["GOOGLE_API_KEY"] = self.google_api_key
            from langchain_google_genai import ChatGoogleGenerativeAI
            
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash-thinking-exp",
                temperature=0,
                max_tokens=None,
                timeout=120,  # Add timeout to prevent hanging
            )
            logger.info("LLM setup successful")
        except ImportError as e:
            logger.error(f"Failed to import required modules: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to setup LLM: {e}")
            raise
    
    def crawl_website(self, url: str, limit: int = 1) -> Optional[str]:
        """
        Crawl a website using Firecrawl to extract markdown content.
        
        Args:
            url: The URL to crawl
            limit: Limit of pages to crawl
            
        Returns:
            Extracted markdown content or None if failed
        """
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=self.firecrawl_api_key)
            
            crawl_result = app.crawl_url(url, params={
                'limit': limit,
                'scrapeOptions': {
                    'formats': ['markdown'],
                }
            })
            
            # Validate response format
            if not crawl_result or 'data' not in crawl_result or not crawl_result['data']:
                logger.error(f"Invalid response format from Firecrawl for URL: {url}")
                return None
                
            context = crawl_result['data'][0].get('markdown')
            if not context:
                logger.error(f"No markdown content found for URL: {url}")
                return None
                
            logger.info(f"Successfully crawled URL: {url}")
            return context
            
        except ImportError as e:
            logger.error(f"Failed to import Firecrawl module: {e}")
            return None
        except Exception as e:
            logger.error(f"Error during website crawling: {e}")
            return None
    
    def _get_extraction_prompt(self, context: str) -> str:
        """
        Create the prompt for LLM extraction.
        
        Args:
            context: The markdown context to extract FAQs from
            
        Returns:
            Formatted prompt string
        """
        return f"""
Task:

Extract frequently asked questions (FAQs) from the given markdown or context.
Read the markdown document from starting to end. Identify the question and you will get the answer till next question starts.
Extract each questions and entire answer for the same question.
Identify and structure the data in JSON format with the following fields:

Expected output:

university_name: The name of the university.
category: The category of the FAQs belongs to .
faqs: A list of FAQs where each item includes:
question: The FAQ question.
answer: A concise response extracted from the markdown or context.
links (if available): Any hyperlinks related to the FAQ, including the display text and URL only if available. Follow strictly
Ensure the extracted text remains accurate and preserves key details. If links are embedded within the answer, extract them separately in a structured format.

Examples: ""
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

""
context:["placeholder","{context}"]/n

"""
    
    def extract_faqs(self, context: str) -> Optional[List[Dict]]:
        """
        Extract FAQs from markdown context using LLM.
        
        Args:
            context: The markdown context to extract FAQs from
            
        Returns:
            List of extracted FAQ dictionaries or None if failed
        """
        if not context:
            logger.error("Cannot extract FAQs from empty context")
            return None
            
        try:
            # Generate prompt and run LLM 
            prompt = self._get_extraction_prompt(context)
            response = self.llm.invoke(prompt)
            
            if not response or not hasattr(response, 'content'):
                logger.error("LLM returned invalid response format")
                return None
                
            # Extract JSON objects using regex from response content
            json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
            matches = re.findall(json_pattern, response.content, re.DOTALL)
            
            if not matches:
                logger.warning("No JSON objects found in LLM response")
                return []
                
            # Process each match
            extracted_data = []
            for match in matches:
                try:
                    json_obj = json.loads(match)
                    extracted_data.append(json_obj)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping invalid JSON: {e}")
                    
            logger.info(f"Successfully extracted {len(extracted_data)} FAQ items")
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error during FAQ extraction: {e}")
            return None
    
    def save_to_json(self, data: List[Dict], file_path: str) -> bool:
        """
        Save extracted FAQs to a JSON file.
        
        Args:
            data: List of FAQ dictionaries to save
            file_path: Path to save the JSON file
            
        Returns:
            True if successful, False otherwise
        """
        if not data:
            logger.warning("No data to save")
            return False
            
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Successfully saved {len(data)} FAQ items to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving to JSON file: {e}")
            return False
    
    def process_url(self, url: str, output_file: str) -> bool:
        """
        Complete process of crawling a URL, extracting FAQs, and saving to JSON.
        
        Args:
            url: URL to extract FAQs from
            output_file: Path to save the extracted FAQs
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Step 1: Crawl website
            context = self.crawl_website(url)
            if not context:
                return False
                
            # Step 2: Extract FAQs
            faqs = self.extract_faqs(context)
            if faqs is None:
                return False
                
            # Step 3: Save to JSON
            return self.save_to_json(faqs, output_file)
            
        except Exception as e:
            logger.error(f"Error in processing URL {url}: {e}")
            return False


def main():
    """Main function to run the FAQ extractor."""
    try:

        # For production, use environment variables instead
        default_firecrawl_api_key = "Your_Key"
        default_google_api_key = "Your_Key"
        
        # Try to get API keys from environment variables first
        firecrawl_api_key = os.environ.get("FIRECRAWL_API_KEY", default_firecrawl_api_key)
        google_api_key = os.environ.get("GOOGLE_API_KEY", default_google_api_key)
        
        
        # Validate API keys
        if not firecrawl_api_key:
            logger.error("FIRECRAWL_API_KEY environment variable is not set")
            return 1
            
        if not google_api_key:
            logger.error("GOOGLE_API_KEY environment variable is not set")
            return 1
        
        # Initialize extractor
        extractor = FAQExtractor(firecrawl_api_key, google_api_key)
        
        # Process URL
        url = "https://www.admissions.txst.edu/contact/faq.html"
        output_file = "texas_FAQ.json"
        
        success = extractor.process_url(url, output_file)
        if success:
            print(f"Successfully extracted FAQs from {url} and saved to {output_file}")
        else:
            print(f"Failed to extract FAQs from {url}")
            
    except Exception as e:
        print(f"An error occurred: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)