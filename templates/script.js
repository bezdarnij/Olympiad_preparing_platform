  function checkPythonFile(file) {
      if (!file) return false;
      
      const fileName = file.name;
      const fileExtension = fileName.toLowerCase().split('.').pop();
      
      return fileExtension === 'py';
  }
  document.addEventListener('DOMContentLoaded', function() {
      const fileInput = document.querySelector('input[type="file"]');
      
      if (fileInput) {
          fileInput.addEventListener('change', function(event) {
              const file = event.target.files[0];
              
              if (file) {
                  if (!checkPythonFile(file)) {
                      alert('ОШИБКА!\n\nРазрешены только файлы с расширением .py\n\Пожалуйста, выберите Python файл (.py)');
                      event.target.value = '';
                  } else {
                      alert('Файл принят!);
                  }
              }
          });
      }
  });
